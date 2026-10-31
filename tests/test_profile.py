from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from model_profile import CONFIG_PATH, load_profile, profile_names  # noqa: E402


class ProfileTest(unittest.TestCase):
    def test_deepseek_profile_keeps_published_values(self) -> None:
        profile = load_profile("deepseek-flash")
        self.assertEqual(profile.model, "deepseek-flash")
        self.assertEqual(profile.alpha, 0.02)
        self.assertEqual(profile.output_over_miss, 4.0)
        self.assertEqual(profile.usd_per_token, 0.15 / 1_000_000)
        self.assertEqual(profile.write_multiplier, 1.0)
        self.assertEqual(
            (profile.min_threshold, profile.max_threshold, profile.threshold_step),
            (64_000, 900_000, 2_000),
        )
        self.assertEqual(profile.context_window, 996_147)
        self.assertEqual(profile.post_context, 17_623)
        self.assertEqual(profile.post_cold_uncached, 13_152)
        self.assertEqual(profile.data_dir, "data/codex/deepseek-flash")
        self.assertEqual(
            profile.compactions_path, "data/codex/deepseek-flash/compactions.json"
        )
        self.assertEqual(profile.harness, "codex")
        self.assertEqual(profile.compaction_cache, "fixed_prefix")

    def test_opus_profile_uses_opus_prices_and_window(self) -> None:
        profile = load_profile("claude-opus-5-5")
        self.assertEqual(profile.harness, "claude-code")
        self.assertEqual(profile.model_prefixes, ("claude-opus-5-5",))
        self.assertEqual(profile.prices["input"], 4.0)
        self.assertEqual(profile.prices["cache_write_1h"], 8.0)
        self.assertEqual(profile.prices["cache_read"], 0.2)
        self.assertEqual(profile.prices["output"], 20.0)
        self.assertAlmostEqual(profile.alpha, 0.05)
        self.assertEqual(profile.write_multiplier, 2.0)
        self.assertEqual(profile.data_dir, "data/claude-code/claude-opus-5-5")
        self.assertEqual(
            profile.compactions_path, "data/claude-code/claude-opus-5-5/compactions.json"
        )
        # Left to be measured from transcripts.
        self.assertIsNone(profile.post_context)

    def test_sonnet_profile_uses_sonnet_prices_and_borrows_calibration(self) -> None:
        profile = load_profile("claude-sonnet-5-5")
        self.assertEqual(profile.model_prefixes, ("claude-sonnet-5-5",))
        self.assertEqual(profile.prices["input"], 2.0)
        self.assertEqual(profile.prices["output"], 10.0)
        self.assertEqual(profile.prices["cache_read"], 0.2)
        self.assertAlmostEqual(profile.alpha, 0.1)
        self.assertEqual(profile.borrow_calibration, "claude-opus-5-5")
        self.assertEqual(profile.data_dir, "data/claude-code/claude-sonnet-5-5")

    def test_every_profile_uses_the_fixed_2k_step(self) -> None:
        for name in profile_names():
            self.assertEqual(load_profile(name).threshold_step, 2_000, name)

    def test_claude_axis_is_the_largest_settable_trigger(self) -> None:
        for name in ("claude-opus-5-5", "claude-sonnet-5-5"):
            profile = load_profile(name)
            trigger = profile.trigger
            buffer = trigger["buffer"]
            self.assertEqual(
                profile.max_threshold,
                min(profile.context_window, trigger["max_window"]) - buffer,
            )
            self.assertEqual(profile.min_threshold, trigger["min_window"] - buffer)
            # Every grid point maps to a round window.
            self.assertEqual((profile.min_threshold + buffer) % 2_000, 0)
        self.assertIsNone(load_profile("deepseek-flash").trigger)

    def test_harness_is_chosen_independently_of_the_profile(self) -> None:
        profile = load_profile("deepseek-flash", "claude-code")
        self.assertEqual(profile.harness, "claude-code")
        self.assertEqual(profile.compaction_cache, "context_minus_tail")
        # Model facts stay those of the profile.
        self.assertEqual(profile.prices["input"], 0.15)
        # Paths follow the (harness, profile) pair.
        self.assertEqual(profile.data_dir, "data/claude-code/deepseek-flash")
        # A pair without a compactions file needs a harness that finds compactions.
        with self.assertRaises(SystemExit):
            load_profile("claude-opus-5-5", "codex")
        with self.assertRaises(SystemExit):
            load_profile("deepseek-flash", "missing")

    def test_unknown_profile_lists_available_names(self) -> None:
        with self.assertRaises(SystemExit) as caught:
            load_profile("missing")
        self.assertIn("deepseek-flash", str(caught.exception))

    def test_every_profile_loads_from_a_custom_file(self) -> None:
        config = json.loads(CONFIG_PATH.read_text())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "models.json"
            path.write_text(json.dumps(config))
            for name in config["profiles"]:
                self.assertEqual(load_profile(name, path=path).name, name)


if __name__ == "__main__":
    unittest.main()
