"""Harness registry: one collector per agent harness, same interface."""

from __future__ import annotations

from pathlib import Path

import harness_claude_code
import harness_codex
from analysis import Collected
from model_profile import Profile


def collect(
    profile: Profile,
    root: Path | None = None,
    *,
    active_thread: str | None = None,
    excluded_threads: list[str] = (),
) -> Collected:
    """Collect the profile's model workload with the profile's harness."""
    root = (root or Path(profile.harness_cfg["root"])).expanduser()
    if profile.harness == "codex":
        return harness_codex.collect(
            root,
            profile,
            active_thread=active_thread,
            excluded_threads=excluded_threads,
        )
    if active_thread or excluded_threads:
        raise SystemExit("--active-thread and --exclude-thread need the codex harness")
    return harness_claude_code.collect(root, profile)
