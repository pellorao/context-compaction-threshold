from __future__ import annotations

import json
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from analysis import (  # noqa: E402
    BootstrapConfig,
    Request,
    Session,
    CompactionSample,
    _replay_session,
    borrow_compactions,
    build_result,
    curve,
    fill_unknown_seconds,
    fit_model,
    fit_request_time,
    load_compactions,
    save_compactions,
)
from model_profile import load_profile  # noqa: E402


class AnalysisTest(unittest.TestCase):
    def test_fit_and_bootstrap_output_are_stable_and_sanitized(self) -> None:
        profile = load_profile("deepseek-flash")
        compactions = load_compactions(ROOT / profile.compactions_path)
        model = fit_model(compactions, profile)
        self.assertGreater(model.time_r2, 0.95)
        self.assertAlmostEqual(model.output_speed, 154.5, delta=0.5)

        session = Session(
            requests=[
                Request(20_000, 13_000, 500, 3.0),
                Request(90_000, 80_000, 700, 4.0),
                Request(180_000, 170_000, 900, 5.0),
                Request(280_000, 270_000, 600, 4.0),
            ],
        )
        result = build_result(
            [session],
            {"smoke-or-test": 1},
            compactions,
            profile,
            BootstrapConfig(replicates=2, block_requests=2, seed=7, workers=1),
            {"uncached_input": 1_000, "cache_write_5m": 0, "cache_write_1h": 0,
             "cache_read": 999_000, "output": 0},
        )
        serialized = json.dumps(result)
        self.assertNotIn("/home/", serialized)
        self.assertNotIn(".jsonl", serialized)
        self.assertEqual(result["snapshot"]["requests"], 4)
        self.assertEqual(len(result["curves"]["central"]), 419)

    def test_cost_is_normalised_by_one_constant_per_profile(self) -> None:
        profile = load_profile("deepseek-flash")
        compactions = load_compactions(ROOT / profile.compactions_path)
        session = Session(
            requests=[Request(20_000, 13_000, 500, 3.0), Request(280_000, 270_000, 600, 4.0)],
        )
        mix = {"uncached_input": 1_000, "cache_write_5m": 0, "cache_write_1h": 0,
               "cache_read": 3_000, "output": 1_000}
        result = build_result(
            [session], {}, compactions, profile,
            BootstrapConfig(replicates=2, block_requests=2, seed=7, workers=1), mix,
        )
        self.assertEqual(result["snapshot"]["billed_tokens"], 5_000)
        self.assertEqual(result["snapshot"]["billing_mix"], mix)
        for row in result["central_curve"] + result["exact_central_curve"]:
            self.assertAlmostEqual(
                row["cost_per_million_tokens"], row["cost_usd_off_peak"] * 200
            )

    def test_compactions_round_trip_and_committed_files_hold_numbers_only(self) -> None:
        samples = [
            CompactionSample("compaction-1", 200_000, 198_000, 4_000, 50.0, "transcript-auto"),
            CompactionSample("compaction-2", 260_000, 258_000, 6_000, 60.5, "transcript-manual"),
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nested" / "compactions.json"
            save_compactions(path, samples)
            self.assertEqual(load_compactions(path), samples)
        for committed in sorted((ROOT / "data").glob("*/*/compactions.json")):
            rows = json.loads(committed.read_text())
            self.assertTrue(rows, committed)
            for row in rows:
                self.assertEqual(
                    set(row),
                    {"name", "source", "input_tokens", "cached_tokens", "output_tokens", "seconds"},
                )
                self.assertRegex(row["name"], r"^[a-z0-9-]{1,20}$")
                self.assertRegex(row["source"], r"^[a-z-]+$")

    def test_borrowed_calibration_rescales_donor_durations(self) -> None:
        profile = load_profile("claude-sonnet-5-5")
        donor = [
            CompactionSample("a", 200_000, 198_000, 4_000, 50.0, "transcript-auto"),
            CompactionSample("b", 260_000, 258_000, 6_000, 60.0, "transcript-auto"),
            CompactionSample("c", 270_000, 267_000, 8_000, 70.0, "transcript-auto"),
        ]
        own = [CompactionSample("x", 250_000, 248_000, 5_000, 110.0, "transcript-auto")]
        compactions, scale = borrow_compactions(own, donor, profile)
        self.assertEqual(len(compactions), 4)
        self.assertGreater(scale, 1.0)
        borrowed = [t for t in compactions if t.name.startswith("borrowed-")]
        self.assertEqual(len(borrowed), 3)
        self.assertTrue(all(t.source.startswith("borrowed-") for t in borrowed))
        self.assertAlmostEqual(borrowed[0].seconds, 50.0 * scale)

    def test_borrow_scale_is_the_median_ratio_so_one_outlier_barely_moves_it(self) -> None:
        profile = load_profile("claude-sonnet-5-5")
        donor = [
            CompactionSample("a", 200_000, 198_000, 4_000, 50.0, "transcript-auto"),
            CompactionSample("b", 260_000, 258_000, 6_000, 60.0, "transcript-auto"),
            CompactionSample("c", 270_000, 267_000, 8_000, 70.0, "transcript-auto"),
        ]
        model = fit_model(donor, profile)

        def own(factor: float) -> CompactionSample:
            predicted = (
                model.seconds_per_uncached * 250_000 + model.seconds_per_output * 5_000
            )
            return CompactionSample("x", 250_000, 248_000, 5_000, predicted * factor, "transcript-auto")

        _, scale = borrow_compactions([own(1.2), own(1.2), own(1.2), own(6.0)], donor, profile)
        self.assertAlmostEqual(scale, 1.2)

    def test_replay_prices_cache_writes_and_compaction_tail(self) -> None:
        profile = load_profile("claude-opus-5-5").with_measured(50_000, 30_000)
        compactions = [
            CompactionSample("a", 200_000, 198_000, 4_000, 50.0, "transcript-auto"),
            CompactionSample("b", 260_000, 258_000, 6_000, 60.0, "transcript-auto"),
            CompactionSample("c", 270_000, 267_000, 8_000, 70.0, "transcript-auto"),
        ]
        model = fit_model(compactions, profile)
        # The compaction input is mostly cache read; only the tail is uncached.
        self.assertEqual(model.central_cached_prefix, 2_000)
        session = Session(
            requests=[
                Request(100_000, 100_000, 0, 10.0),
                Request(300_000, 300_000, 0, 10.0),
            ],
            uncached_multiplier=2.0,
        )
        result = _replay_session(
            session,
            200_000,
            model,
            profile,
            cached_prefix=model.central_cached_prefix,
        )
        self.assertEqual(result["compactions"], 1)
        self.assertGreater(result["compaction_seconds"], 0)
        self.assertEqual(result["request_seconds"], 20.0)
        # compaction: 300k context, 2k uncached written at 2x, rest read
        # 100k first request is all cache read; post-compaction request has
        # 30k written at 2x and 20k read.
        alpha = profile.alpha
        out = profile.output_over_miss
        expected_tokens = 298_000 * alpha + 2_000 * 2.0 + 100_000 * alpha
        expected_tokens += 30_000 * 2.0 + 20_000 * alpha
        self.assertGreater(result["cost_units"], expected_tokens)
        self.assertLess(
            result["cost_units"] - expected_tokens,
            out * 20_000,  # only the summary output remains
        )

    def test_time_share_is_compaction_seconds_over_all_request_seconds(self) -> None:
        profile = load_profile("deepseek-flash")
        model = fit_model(load_compactions(ROOT / profile.compactions_path), profile)
        # 100 requests of 5 s each; the context passes any low threshold once.
        requests = [Request(20_000 + 1_000 * i, 19_000 + 1_000 * i, 100, 5.0) for i in range(100)]
        rows = curve(
            [Session(requests)], model, profile, cached_prefix=model.central_cached_prefix
        )
        low = rows[0]
        self.assertEqual(low["request_seconds"], 500.0)
        self.assertGreater(low["compactions"], 0)
        self.assertAlmostEqual(
            low["time_share"],
            low["compaction_seconds"] / (500.0 + low["compaction_seconds"]),
        )
        # Never compacting: no compaction seconds, share zero.
        self.assertEqual(rows[-1]["compactions"], 0)
        self.assertEqual(rows[-1]["time_share"], 0.0)

    def test_unknown_request_durations_get_the_median_of_the_known_ones(self) -> None:
        sessions = [
            Session([Request(1, 1, 1, 2.0), Request(1, 1, 1, 0.0)]),
            Session([Request(1, 1, 1, 6.0), Request(1, 1, 1, -3.0), Request(1, 1, 1, 10.0)]),
        ]
        self.assertEqual(fill_unknown_seconds(sessions), 2)
        self.assertEqual(
            [[r.seconds for r in s.requests] for s in sessions],
            [[2.0, 6.0], [6.0, 6.0, 10.0]],
        )

    def test_summary_size_is_constant_on_codex_and_linear_on_claude_code(self) -> None:
        codex = load_profile("deepseek-flash")
        samples = load_compactions(ROOT / codex.compactions_path)
        model = fit_model(samples, codex)
        self.assertEqual(model.summary_per_input, 0.0)
        self.assertAlmostEqual(
            model.summary_intercept,
            sum(item.output_tokens for item in samples) / len(samples),
        )
        claude = load_profile("claude-opus-5-5")
        model = fit_model(load_compactions(ROOT / claude.compactions_path), claude)
        self.assertGreater(model.summary_per_input, 0)


if __name__ == "__main__":
    unittest.main()


class RequestTimeTest(unittest.TestCase):
    def test_slope_fit_recovers_context_and_output_effects(self) -> None:
        # seconds = 1 + 4e-6 * context + 0.01 * output, exactly.
        requests = [
            Request(c, c, o, 1 + 4e-6 * c + 0.01 * o)
            for c, o in [(10_000, 100), (50_000, 900), (120_000, 200), (300_000, 700), (80_000, 50)]
        ]
        fit = fit_request_time([Session(requests)])
        self.assertAlmostEqual(fit.seconds_per_input, 4e-6, places=11)
        self.assertAlmostEqual(fit.seconds_per_output, 0.01, places=8)
        self.assertAlmostEqual(fit.intercept, 1.0, places=6)
        self.assertAlmostEqual(fit.r2, 1.0, places=9)

    def test_fit_uses_the_observed_context_not_the_chained_one(self) -> None:
        chained = [Request(c + 500_000, c + 500_000, c % 700, 1 + 4e-6 * c, c) for c in (10_000, 90_000, 200_000, 60_000)]
        self.assertAlmostEqual(
            fit_request_time([Session(chained)]).seconds_per_input, 4e-6, places=11
        )

    def test_replayed_request_seconds_follow_the_context_shift(self) -> None:
        profile = load_profile("deepseek-flash")
        model = fit_model(load_compactions(ROOT / profile.compactions_path), profile)
        # Observed contexts 20K..119K; a 5 s request each.
        requests = [Request(20_000 + 1_000 * i, 19_000 + 1_000 * i, 100, 5.0) for i in range(100)]
        slopes = (1e-5, 0.0, 2e-5)
        rows = curve(
            [Session(requests)], model, profile,
            cached_prefix=model.central_cached_prefix, slopes=slopes,
        )
        # Never compacting: the replayed context is the observed one, no shift.
        never = rows[-1]
        self.assertEqual(never["context_shift_tokens"], 0)
        self.assertEqual(never["request_seconds"], 500.0)
        # A low trigger compacts to a smaller context: requests get faster,
        # linearly in the slope, and the share uses the adjusted seconds.
        low = rows[0]
        self.assertLess(low["context_shift_tokens"], 0)
        self.assertAlmostEqual(
            low["request_seconds"], 500.0 + 1e-5 * low["context_shift_tokens"]
        )
        self.assertEqual(low["request_seconds_slope_lo"], 500.0)
        self.assertAlmostEqual(
            low["request_seconds_slope_hi"], 500.0 + 2e-5 * low["context_shift_tokens"]
        )
        self.assertAlmostEqual(
            low["time_share"],
            low["compaction_seconds"] / (low["request_seconds"] + low["compaction_seconds"]),
        )

    def test_result_stores_slope_interval_and_per_row_request_seconds(self) -> None:
        profile = replace(load_profile("deepseek-flash"), request_slope=None)
        compactions = load_compactions(ROOT / profile.compactions_path)
        sessions = [
            Session([Request(20_000 + 3_000 * i, 18_000 + 3_000 * i, 100 + 7 * (i % 5), 2.0 + 3e-6 * (20_000 + 3_000 * i) + 0.01 * (100 + 7 * (i % 5))) for i in range(40)])
            for _ in range(3)
        ]
        result = build_result(
            sessions, {}, compactions, profile,
            BootstrapConfig(replicates=6, block_requests=4, seed=3, workers=1),
            {"uncached_input": 1_000, "cache_write_5m": 0, "cache_write_1h": 0,
             "cache_read": 999_000, "output": 0},
        )
        fit = result["fitted_model"]
        self.assertAlmostEqual(fit["request_seconds_per_context_token"], 3e-6, places=9)
        self.assertLessEqual(
            fit["request_seconds_per_context_token_low"],
            fit["request_seconds_per_context_token_high"],
        )
        row = result["curves"]["central"][0]
        for key in ("request_seconds", "request_seconds_slope_lo", "request_seconds_slope_hi"):
            self.assertIn(key, row)

    def test_measured_slope_replaces_the_fitted_one(self) -> None:
        profile = load_profile("deepseek-flash")
        self.assertEqual(profile.request_slope, (0.96e-5, 0.31e-5, 1.18e-5))
        compactions = load_compactions(ROOT / profile.compactions_path)
        sessions = [Session([Request(20_000 + 3_000 * i, 18_000 + 3_000 * i, 100, 2.0 + 3e-6 * (20_000 + 3_000 * i)) for i in range(40)])]
        result = build_result(
            sessions, {}, compactions, profile,
            BootstrapConfig(replicates=4, block_requests=4, seed=3, workers=1),
            {"uncached_input": 1_000, "cache_write_5m": 0, "cache_write_1h": 0,
             "cache_read": 999_000, "output": 0},
        )
        fit = result["fitted_model"]
        self.assertEqual(fit["request_slope_source"], "controlled")
        self.assertEqual(fit["request_seconds_per_context_token"], 0.96e-5)
        self.assertEqual(fit["request_seconds_per_context_token_low"], 0.31e-5)
        self.assertEqual(fit["request_seconds_per_context_token_high"], 1.18e-5)
        self.assertAlmostEqual(fit["request_seconds_per_context_token_log_fit"], 3e-6, places=9)
        row = result["curves"]["central"][0]
        self.assertAlmostEqual(
            row["request_seconds"] - row["request_seconds_slope_lo"],
            (0.96e-5 - 0.31e-5) * row["context_shift_tokens"],
        )
