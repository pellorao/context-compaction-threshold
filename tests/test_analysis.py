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
    build_result,
    fit_model,
    load_trials,
)


class AnalysisTest(unittest.TestCase):
    def test_fit_and_bootstrap_output_are_stable_and_sanitized(self) -> None:
        trials = load_trials(ROOT / "data" / "compaction_trials.json")
        model = fit_model(trials)
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
            BootstrapConfig(replicates=2, block_requests=2, seed=7, workers=1),
        )
        serialized = json.dumps(result)
        self.assertNotIn("/home/", serialized)
        self.assertNotIn(".jsonl", serialized)
        self.assertEqual(result["snapshot"]["requests"], 4)
        self.assertEqual(len(result["curves"]["central"]), 419)


if __name__ == "__main__":
    unittest.main()
