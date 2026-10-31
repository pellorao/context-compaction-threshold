"""Model profiles and harness settings, both read from config/models.json.

A profile holds model facts (prices, context window, model-name filter, label).
A harness holds how the logs are collected (default root, compaction handling,
how the trigger is set). A run is one (profile, harness) pair. Page text lives
in config/pages.json.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "models.json"
DEFAULT_PROFILE = "deepseek-flash"
DEFAULT_HARNESS = "codex"
COMPACTIONS_NAME = "compactions.json"


@dataclass(frozen=True)
class Profile:
    name: str
    label: str
    model: str
    model_prefixes: tuple[str, ...]
    provider: str | None
    prices: dict
    context_window: int
    min_threshold: int
    max_threshold: int
    threshold_step: int
    time_limit: float
    quick_limits: tuple[float, ...]
    time_axis_max: float
    speed_slider: dict
    post_context: int | None
    post_cold_uncached: int | None
    min_summary: int
    range_quantiles: tuple[float, float]
    # Repository-relative directory of this (harness, profile) pair's data:
    # compactions.json and result.json.
    data_dir: str
    # Profile whose compactions top up this model's when it has too few.
    borrow_calibration: str | None
    harness: str
    harness_cfg: dict
    # Measured request-duration slope (central, low, high; seconds per context
    # token) that replaces the log fit and its bootstrap interval, or None.
    request_slope: tuple[float, float, float] | None = None

    @property
    def compactions_path(self) -> str:
        return f"{self.data_dir}/{COMPACTIONS_NAME}"

    @property
    def alpha(self) -> float:
        return self.prices["cache_read"] / self.prices["input"]

    @property
    def output_over_miss(self) -> float:
        return self.prices["output"] / self.prices["input"]

    @property
    def usd_per_token(self) -> float:
        return self.prices["input"] / 1_000_000

    @property
    def write_multiplier(self) -> float:
        return self.prices["cache_write_1h"] / self.prices["input"]

    @property
    def trigger(self) -> dict | None:
        """How the user sets the trigger in this harness, or None."""
        return self.harness_cfg["trigger"]

    @property
    def compaction_cache(self) -> str:
        return self.harness_cfg["compaction_cache"]

    @property
    def prefill_time_on_total(self) -> bool:
        return self.harness_cfg["prefill_time_on_total"]

    @property
    def summary_grows_with_input(self) -> bool:
        return self.harness_cfg["summary_grows_with_input"]

    def with_measured(self, post_context: int, post_cold_uncached: int) -> "Profile":
        """Fill post-compaction values the profile leaves to the logs."""
        return replace(
            self,
            post_context=self.post_context or post_context,
            post_cold_uncached=self.post_cold_uncached or post_cold_uncached,
        )


def load_profile(
    name: str,
    harness: str | None = None,
    path: Path = CONFIG_PATH,
) -> Profile:
    config = json.loads(path.read_text())
    profiles, harnesses = config["profiles"], config["harnesses"]
    if name not in profiles:
        raise SystemExit(
            f"Unknown profile {name!r}; available: {', '.join(sorted(profiles))}"
        )
    raw = profiles[name]
    harness = harness or raw.get("harness", DEFAULT_HARNESS)
    if harness not in harnesses:
        raise SystemExit(
            f"Unknown harness {harness!r}; available: {', '.join(sorted(harnesses))}"
        )
    cfg = harnesses[harness]
    # Inputs and results of a pair live together in data/<harness>/<profile>/.
    data_dir = f"data/{harness}/{name}"
    threshold = raw["threshold"]
    post = raw["post_compaction"] or {}
    return Profile(
        name=name,
        label=raw["label"],
        model=raw["model"],
        model_prefixes=tuple(raw["model_prefixes"]),
        provider=raw["provider"],
        prices=raw["prices_usd_per_million"],
        context_window=raw["context_window"],
        min_threshold=threshold["min"],
        max_threshold=threshold["max"],
        threshold_step=threshold["step"],
        time_limit=raw["time_limit"],
        quick_limits=tuple(raw["quick_limits"]),
        time_axis_max=raw["time_axis_max"],
        speed_slider=raw["speed_slider"],
        post_context=post.get("context"),
        post_cold_uncached=post.get("cold_uncached"),
        min_summary=raw["min_summary"],
        range_quantiles=tuple(raw["range_quantiles"]),
        data_dir=data_dir,
        borrow_calibration=raw.get("borrow_calibration"),
        harness=harness,
        harness_cfg=cfg,
        request_slope=tuple(raw["request_slope"]) if "request_slope" in raw else None,
    )


def profile_names(path: Path = CONFIG_PATH) -> list[str]:
    return list(json.loads(path.read_text())["profiles"])
