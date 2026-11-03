#!/usr/bin/env python3
"""Analyze a model profile and publish the static site (landing page + one page per model)."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from analysis import (
    LOGGED_SOURCES,
    BootstrapConfig,
    FitError,
    borrow_compactions,
    build_result,
    load_compactions,
    save_compactions,
)
from harness import collect
from model_profile import (
    COMPACTIONS_NAME,
    DEFAULT_PROFILE,
    ROOT,
    Profile,
    load_profile,
    profile_names,
)
from render import LANDING_NAME, load_pages, render_landing, render_model

SITE_DIR = ROOT / "artifacts"


def snapshot_time(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise argparse.ArgumentTypeError("Use an ISO timestamp with a timezone") from error
    if parsed.tzinfo is None:
        raise argparse.ArgumentTypeError("The snapshot timestamp needs a timezone")
    return parsed.astimezone(timezone.utc)


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
        "--compactions",
        type=Path,
        help="Compaction samples file (default: the profile's compactions.json)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Directory for result.json (default: data/<harness>/<profile>)",
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
    parser.add_argument(
        "--snapshot-at", type=snapshot_time,
        help="UTC/offset timestamp anchoring the profile's recent-session window (default: now)",
    )
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
        snapshot_at=args.snapshot_at,
    )
    profile = collected.profile
    committed_path = ROOT / profile.compactions_path
    # A run sent to another directory keeps its samples there too, so the
    # committed file is never rewritten by it.
    redirected = output_dir.resolve() != (ROOT / profile.data_dir).resolve()
    compactions_path = args.compactions or (
        output_dir / COMPACTIONS_NAME if redirected else committed_path
    )
    if not args.compactions:
        # Samples found in the logs are stored (the hand-measured ones already
        # in the committed file stay); the fit reads the stored file.
        hand = (
            [
                s
                for s in load_compactions(committed_path)
                if not s.source.startswith(LOGGED_SOURCES)
            ]
            if committed_path.exists()
            else []
        )
        # A compaction that was also timed by hand keeps its hand timing.
        timed = {(h.input_tokens, h.cached_tokens, h.output_tokens) for h in hand}
        found = [
            c
            for c in collected.compactions
            if (c.input_tokens, c.cached_tokens, c.output_tokens) not in timed
        ]
        output_dir.mkdir(parents=True, exist_ok=True)
        save_compactions(compactions_path, hand + found)
    compactions = load_compactions(compactions_path)
    stats = dict(collected.stats)
    needed = profile.harness_cfg.get("min_fit_compactions", 0)
    if len(compactions) < needed:
        if not profile.borrow_calibration:
            raise SystemExit(
                f"Only {len(compactions)} compactions found for {profile.name}; "
                f"at least {needed} are needed to fit the time model "
                "(or set borrow_calibration in the profile)"
            )
        donor = load_compactions(
            ROOT / load_profile(profile.borrow_calibration, profile.harness).compactions_path
        )
        own = len(compactions)
        compactions, scale = borrow_compactions(compactions, donor, profile)
        stats["calibration_borrowed"] = {
            "donor": profile.borrow_calibration,
            "own": own,
            "borrowed": len(donor),
            "scale": scale,
        }
    result = build_result(
        collected.sessions,
        collected.excluded,
        compactions,
        profile,
        config,
        collected.billing_mix,
        stats,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "result.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    )
    snapshot = result["snapshot"]
    print(
        f"{snapshot['requests']} requests, "
        f"{snapshot['request_seconds']:.1f} request-seconds, "
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
    (site_dir / LANDING_NAME).write_text(landing)
    print(site_dir / LANDING_NAME)


def main() -> None:
    args = parse_args()
    analyzed = load_profile(args.profile, args.harness)
    analyzed_dir = args.output_dir or ROOT / analyzed.data_dir
    if not args.render_only:
        try:
            analyze(args, analyzed, analyzed_dir)
        except FitError as error:
            raise SystemExit(str(error)) from error
    profiles: dict[str, Profile] = {}
    results: dict[str, dict] = {}
    for name in profile_names():
        profile = analyzed if name == args.profile else load_profile(name)
        result_path = (analyzed_dir if name == args.profile else ROOT / profile.data_dir) / "result.json"
        if result_path.exists():
            profiles[name] = profile
            results[name] = json.loads(result_path.read_text())
    write_site(args.site_dir, results, profiles)


if __name__ == "__main__":
    main()
