from __future__ import annotations

import json
import sys
import tempfile
import unittest
from argparse import Namespace
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import generate  # noqa: E402
from analysis import (  # noqa: E402
    CompactionSample,
    FitError,
    Request,
    Session,
    _minimum_valid,
    check_threshold_floor,
    fill_unknown_seconds,
    fit_request_time,
    load_compactions,
)
from harness_claude_code import _fit_token_estimator  # noqa: E402
from harness_codex import _has_marker  # noqa: E402
from model_profile import load_profile, profile_names  # noqa: E402


def plain_answer(cjk: int, other: int, tokens: int) -> SimpleNamespace:
    return SimpleNamespace(
        text_cjk=cjk, text_other=other, stop_reason="end_turn", text_only=True,
        output_tokens=tokens, thinking_tokens=0,
    )


class ThresholdFloorTest(unittest.TestCase):
    def test_published_grids_start_above_the_post_compaction_context(self) -> None:
        for name in profile_names():
            profile = load_profile(name)
            result = json.loads((ROOT / profile.data_dir / "result.json").read_text())
            post = result["fitted_model"]["post_compaction_context"]
            self.assertGreater(profile.min_threshold, post, name)
            self.assertEqual(result["snapshot"]["reliability_floor"], profile.min_threshold)

    def test_a_grid_at_or_below_the_post_compaction_context_is_refused(self) -> None:
        profile = load_profile("gpt-6.1-terra")
        check_threshold_floor(replace(profile, post_context=None))
        check_threshold_floor(replace(profile, post_context=profile.min_threshold - 1))
        with self.assertRaises(FitError):
            check_threshold_floor(replace(profile, post_context=profile.min_threshold))


class DegenerateInputTest(unittest.TestCase):
    def test_constant_features_give_a_clear_error(self) -> None:
        constant = Session([Request(10_000 + 1_000 * i, 9_000, 100, 1.0) for i in range(5)])
        with self.assertRaises(FitError):
            fit_request_time([constant])
        with self.assertRaises(FitError):
            fit_request_time([])
        with self.assertRaises(FitError):
            fill_unknown_seconds([Session([Request(1, 1, 1, 0.0)])])

    def test_token_estimator_without_cjk_uses_one_rate(self) -> None:
        messages = [plain_answer(0, 200 * n, 100 * n) for n in range(1, 4)]
        per_cjk, per_other, count = _fit_token_estimator([SimpleNamespace(messages=messages)])
        self.assertAlmostEqual(per_other, 0.5)
        self.assertEqual(per_cjk, per_other)
        self.assertEqual(count, 3)
        with self.assertRaises(FitError):
            _fit_token_estimator([SimpleNamespace(messages=[])])

    def test_no_feasible_row_gives_no_optimum(self) -> None:
        self.assertIsNone(_minimum_valid([{"feasible_time": False, "cost_usd_off_peak": 1.0}]))


class CwdMarkerTest(unittest.TestCase):
    def test_markers_match_words_not_substrings(self) -> None:
        markers = ["smoke", "probe", "test"]
        for cwd in ("/work/tests", "/work/test-app", "/tmp/smoke_run", "/work/testbed"):
            self.assertTrue(_has_marker(cwd, markers), cwd)
        for cwd in ("/work/latest", "/work/contest", "/work/app"):
            self.assertFalse(_has_marker(cwd, markers), cwd)


class OutputDirTest(unittest.TestCase):
    def test_a_redirected_run_leaves_the_committed_samples_alone(self) -> None:
        profile = load_profile("deepseek-flash")
        committed = ROOT / profile.compactions_path
        before = committed.read_bytes()
        logged = CompactionSample("log-1", 100_000, 90_000, 1_000, 30.0, "log-auto")
        collected = SimpleNamespace(
            profile=profile, compactions=[logged], stats={}, sessions=[],
            excluded={}, billing_mix={},
        )
        args = Namespace(
            compactions=None, replicates=1, block_size=1, seed=1, workers=1,
            session_root=None, active_thread=None, exclude_thread=[], snapshot_at=None,
        )
        with tempfile.TemporaryDirectory() as directory, \
                mock.patch.object(generate, "collect", return_value=collected), \
                mock.patch.object(generate, "build_result", side_effect=RuntimeError("stop")):
            with self.assertRaises(RuntimeError):
                generate.analyze(args, profile, Path(directory))
            stored = load_compactions(Path(directory) / "compactions.json")
        self.assertEqual(committed.read_bytes(), before)
        self.assertIn("log-1", [s.name for s in stored])
        self.assertTrue(any(not s.source.startswith(generate.LOGGED_SOURCES) for s in stored))


if __name__ == "__main__":
    unittest.main()
