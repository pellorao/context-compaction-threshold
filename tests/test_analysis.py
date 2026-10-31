from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from analysis import (  # noqa: E402
    BootstrapConfig,
    Request,
    Session,
    Trial,
    _replay_session,
    borrow_trials,
    build_result,
    fit_model,
    load_trials,
)
from model_profile import load_profile  # noqa: E402


class AnalysisTest(unittest.TestCase):
    def test_fit_and_bootstrap_output_are_stable_and_sanitized(self) -> None:
        profile = load_profile("deepseek-flash")
        trials = load_trials(ROOT / profile.trials_path)
        model = fit_model(trials, profile)
        self.assertGreater(model.time_r2, 0.95)
        self.assertAlmostEqual(model.output_speed, 167.5, delta=0.5)

        session = Session(
            requests=[
                Request(20_000, 13_000, 500),
                Request(90_000, 80_000, 700),
                Request(180_000, 170_000, 900),
                Request(280_000, 270_000, 600),
            ],
            task_seconds=120,
        )
        result = build_result(
            [session],
            {"smoke-or-test": 1},
            trials,
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
        trials = load_trials(ROOT / profile.trials_path)
        session = Session(
            requests=[Request(20_000, 13_000, 500), Request(280_000, 270_000, 600)],
            task_seconds=60,
        )
        mix = {"uncached_input": 1_000, "cache_write_5m": 0, "cache_write_1h": 0,
               "cache_read": 3_000, "output": 1_000}
        result = build_result(
            [session], {}, trials, profile,
            BootstrapConfig(replicates=2, block_requests=2, seed=7, workers=1), mix,
        )
        self.assertEqual(result["snapshot"]["billed_tokens"], 5_000)
        self.assertEqual(result["snapshot"]["billing_mix"], mix)
        for row in result["central_curve"] + result["exact_central_curve"]:
            self.assertAlmostEqual(
                row["cost_per_million_tokens"], row["cost_usd_off_peak"] * 200
            )

    def test_borrowed_calibration_rescales_donor_durations(self) -> None:
        profile = load_profile("claude-sonnet-5-5")
        donor = [
            Trial("a", 200_000, 198_000, 4_000, 50.0, "auto"),
            Trial("b", 260_000, 258_000, 6_000, 60.0, "auto"),
            Trial("c", 270_000, 267_000, 8_000, 70.0, "auto"),
        ]
        own = [Trial("x", 250_000, 248_000, 5_000, 110.0, "auto")]
        trials, scale = borrow_trials(own, donor, profile)
        self.assertEqual(len(trials), 4)
        self.assertGreater(scale, 1.0)
        borrowed = [t for t in trials if t.name.startswith("borrowed-")]
        self.assertEqual(len(borrowed), 3)
        self.assertTrue(all(t.source.startswith("borrowed-") for t in borrowed))
        self.assertAlmostEqual(borrowed[0].seconds, 50.0 * scale)

    def test_replay_prices_cache_writes_and_compaction_tail(self) -> None:
        profile = load_profile("claude-opus-5-5").with_measured(50_000, 30_000)
        trials = [
            Trial("a", 200_000, 198_000, 4_000, 50.0, "auto"),
            Trial("b", 260_000, 258_000, 6_000, 60.0, "auto"),
            Trial("c", 270_000, 267_000, 8_000, 70.0, "auto"),
        ]
        model = fit_model(trials, profile)
        # The compaction input is mostly cache read; only the tail is uncached.
        self.assertEqual(model.central_cached_prefix, 2_000)
        session = Session(
            requests=[
                Request(100_000, 100_000, 0),
                Request(300_000, 300_000, 0),
            ],
            task_seconds=100,
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


if __name__ == "__main__":
    unittest.main()
