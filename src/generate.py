#!/usr/bin/env python3
"""Analyze a model profile and publish the static site (landing page + one page per model)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from analysis import BootstrapConfig, borrow_trials, build_result, load_trials
from harness import collect
from model_profile import (
    DEFAULT_PROFILE,
    ROOT,
    Profile,
    load_profile,
    profile_names,
)
from render import LANDING_NAME, load_pages, render_landing, render_model

SITE_DIR = ROOT / "artifacts"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--profile",
        default=DEFAULT_PROFILE,
        help="Model profile name from config/models.json "
        f"(default: {DEFAULT_PROFILE})",
    )
    parser.add_argument(
        "--harness",
        help="Harness that collects the logs: codex or claude-code "
        "(default: the profile's harness, else codex)",
    )
    parser.add_argument(
        "--render-only",
        action="store_true",
        help="Skip the analysis and rebuild the site from the existing result.json files",
    )
    parser.add_argument(
        "--session-root",
        type=Path,
        help="Session JSONL root (default: the harness's root)",
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
        help="Compaction trials file (default: the profile's trials file)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Directory for result.json and curves.csv (default: the profile's output_dir)",
    )
    parser.add_argument(
        "--site-dir",
        type=Path,
        default=SITE_DIR,
        help=f"Directory for the generated pages (default: {SITE_DIR})",
    )
    parser.add_argument("--replicates", type=int, default=100)
    parser.add_argument("--block-size", type=int, default=8)
    parser.add_argument("--seed", type=int, default=20_261_031)
    parser.add_argument("--workers", type=int, default=BootstrapConfig().workers)
    return parser.parse_args()


def analyze(args: argparse.Namespace, profile: Profile, output_dir: Path) -> None:
    config = BootstrapConfig(
        replicates=args.replicates,
        block_requests=args.block_size,
        seed=args.seed,
        workers=args.workers,
    )
    collected = collect(
        profile,
        args.session_root,
        active_thread=args.active_thread,
        excluded_threads=args.exclude_thread,
    )
    profile = collected.profile
    trials_path = args.trials or (
        ROOT / profile.trials_path if profile.trials_path else None
    )
    stats = dict(collected.stats)
    if trials_path:
        trials = load_trials(trials_path)
    else:
        trials = collected.trials
        needed = profile.harness_cfg["min_fit_compactions"]
        if len(trials) < needed:
            if not profile.borrow_calibration:
                raise SystemExit(
                    f"Only {len(trials)} compactions found for {profile.name}; "
                    f"at least {needed} are needed to fit the time model "
                    "(or set borrow_calibration in the profile)"
                )
            donor = collect(
                load_profile(profile.borrow_calibration, profile.harness),
                args.session_root,
            )
            own = len(trials)
            trials, scale = borrow_trials(trials, donor.trials, profile)
            stats["calibration_borrowed"] = {
                "donor": profile.borrow_calibration,
                "own": own,
                "borrowed": len(donor.trials),
                "scale": scale,
            }
    result = build_result(
        collected.sessions,
        collected.excluded,
        trials,
        profile,
        config,
        collected.billing_mix,
        stats,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "result.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    )
    with (output_dir / "curves.csv").open("w") as stream:
        stream.write(
            "threshold,expected_cost_usd,expected_compactions,"
            "expected_compaction_seconds,expected_time_share,"
            "expected_cost_usd_per_million_tokens\n"
        )
        for row in result["curves"]["central"]:
            stream.write(
                f"{row['threshold']},"
                f"{row['cost_usd_off_peak']:.6f},"
                f"{row['compactions']:.6f},"
                f"{row['compaction_seconds']:.6f},"
                f"{row['time_share']:.8f},"
                f"{row['cost_per_million_tokens']:.6f}\n"
            )
    snapshot = result["snapshot"]
    print(
        f"{snapshot['requests']} requests, "
        f"{snapshot['work_seconds']:.1f} work-seconds, "
        f"{snapshot['included_sessions']} independent sessions"
        + (" + active tail" if snapshot["included_active_tail"] else "")
    )


def write_site(site_dir: Path, results: dict[str, dict], profiles: dict[str, Profile]) -> None:
    pages = load_pages()
    labels = {name: profile.label for name, profile in profiles.items()}
    site_dir.mkdir(parents=True, exist_ok=True)
    for name, data in results.items():
        (site_dir / f"{name}.html").write_text(
            render_model(data, profiles[name], pages, labels)
        )
    landing = render_landing(results, profiles, pages, labels)
    # Cloudflare Pages copies threshold-chart.html to index.html; write both names.
    (site_dir / LANDING_NAME).write_text(landing)
    (site_dir / "index.html").write_text(landing)
    print(site_dir / LANDING_NAME)


def main() -> None:
    args = parse_args()
    analyzed = load_profile(args.profile, args.harness)
    analyzed_dir = args.output_dir or ROOT / analyzed.output_dir
    if not args.render_only:
        analyze(args, analyzed, analyzed_dir)
    profiles: dict[str, Profile] = {}
    results: dict[str, dict] = {}
    for name in profile_names():
        profile = analyzed if name == args.profile else load_profile(name)
        result_path = (analyzed_dir if name == args.profile else ROOT / profile.output_dir) / "result.json"
        if result_path.exists():
            profiles[name] = profile
            results[name] = json.loads(result_path.read_text())
    write_site(args.site_dir, results, profiles)


if __name__ == "__main__":
    main()
