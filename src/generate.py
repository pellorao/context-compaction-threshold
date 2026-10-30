#!/usr/bin/env python3
"""Generate the DeepSeek compaction threshold report."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from analysis import BootstrapConfig, build_result, load_trials, load_workload
from render import render


ROOT = Path(__file__).resolve().parent.parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--session-root",
        type=Path,
        default=Path.home() / ".codex" / "sessions",
        help="Codex session JSONL root (default: ~/.codex/sessions)",
    )
    parser.add_argument(
        "--active-thread",
        help="Exclude this analysis thread and include its latest post-compaction tail",
    )
    parser.add_argument(
        "--exclude-thread",
        action="append",
        default=[],
        help="Additional session thread to exclude; may be repeated",
    )
    parser.add_argument(
        "--trials",
        type=Path,
        default=ROOT / "data" / "compaction_trials.json",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "artifacts",
    )
    parser.add_argument("--replicates", type=int, default=100)
    parser.add_argument("--block-size", type=int, default=8)
    parser.add_argument("--seed", type=int, default=20_261_031)
    parser.add_argument("--workers", type=int, default=BootstrapConfig().workers)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    sessions, excluded = load_workload(
        args.session_root,
        active_thread=args.active_thread,
        excluded_threads=args.exclude_thread,
    )
    config = BootstrapConfig(
        replicates=args.replicates,
        block_requests=args.block_size,
        seed=args.seed,
        workers=args.workers,
    )
    result = build_result(
        sessions,
        excluded,
        load_trials(args.trials),
        config,
    )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "result.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    )
    (args.output_dir / "threshold-chart.html").write_text(render(result))
    with (args.output_dir / "curves.csv").open("w") as stream:
        stream.write(
            "threshold,expected_cost_usd,expected_compactions,"
            "expected_compaction_seconds,expected_time_share\n"
        )
        for row in result["curves"]["central"]:
            stream.write(
                f"{row['threshold']},"
                f"{row['cost_usd_off_peak']:.6f},"
                f"{row['compactions']:.6f},"
                f"{row['compaction_seconds']:.6f},"
                f"{row['time_share']:.8f}\n"
            )

    snapshot = result["snapshot"]
    print(
        f"{snapshot['requests']} requests, "
        f"{snapshot['work_seconds']:.1f} work-seconds, "
        f"{snapshot['included_sessions']} independent sessions"
        + (" + active tail" if snapshot["included_active_tail"] else "")
    )
    print(args.output_dir / "threshold-chart.html")


if __name__ == "__main__":
    main()
