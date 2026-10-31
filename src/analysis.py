"""Analyze compaction thresholds from local agent session logs."""

from __future__ import annotations

import json
import math
import os
import random
import statistics
from dataclasses import dataclass, replace
from datetime import datetime
from multiprocessing import Pool
from pathlib import Path

from model_profile import Profile


@dataclass(frozen=True)
class Request:
    input_tokens: int
    cached_tokens: int
    output_tokens: int


@dataclass
class Session:
    requests: list[Request]
    task_seconds: float
    segment: str | None = None
    # Price of an uncached token relative to the plain input price (cache
    # writes cost more than plain input on some models).
    uncached_multiplier: float = 1.0


@dataclass(frozen=True)
class CompactionSample:
    name: str
    input_tokens: int
    cached_tokens: int
    output_tokens: int
    seconds: float
    source: str


@dataclass
class Collected:
    """What a harness returns: the workload and any compactions found in logs."""

    sessions: list[Session]
    excluded: dict[str, int]
    compactions: list[CompactionSample] | None
    profile: Profile
    stats: dict
    # Billed tokens of the real history by price class: uncached_input,
    # cache_write_5m, cache_write_1h, cache_read, output.
    billing_mix: dict[str, int]


@dataclass(frozen=True)
class BootstrapConfig:
    replicates: int = 100
    block_requests: int = 8
    seed: int = 20_261_031
    workers: int = min(8, os.cpu_count() or 1)


def parse_timestamp(value: str) -> float:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def save_compactions(path: Path, samples: list[CompactionSample]) -> None:
    """Write samples (numbers and a source label only) next to the other inputs."""
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        {
            "name": item.name,
            "source": item.source,
            "input_tokens": item.input_tokens,
            "cached_tokens": item.cached_tokens,
            "output_tokens": item.output_tokens,
            "seconds": item.seconds,
        }
        for item in samples
    ]
    path.write_text(json.dumps(rows, indent=2) + "\n")


def load_compactions(path: Path) -> list[CompactionSample]:
    raw = json.loads(path.read_text())
    return [
        CompactionSample(
            name=item["name"],
            input_tokens=int(item["input_tokens"]),
            cached_tokens=int(item["cached_tokens"]),
            output_tokens=int(item["output_tokens"]),
            seconds=float(item["seconds"]),
            source=item["source"],
        )
        for item in raw
    ]


def _solve_linear(matrix: list[list[float]], vector: list[float]) -> list[float]:
    size = len(vector)
    rows = [matrix[index][:] + [vector[index]] for index in range(size)]
    for column in range(size):
        pivot = max(range(column, size), key=lambda row: abs(rows[row][column]))
        rows[column], rows[pivot] = rows[pivot], rows[column]
        divisor = rows[column][column]
        rows[column] = [value / divisor for value in rows[column]]
        for row in range(size):
            if row == column:
                continue
            factor = rows[row][column]
            rows[row] = [
                value - factor * pivot_value
                for value, pivot_value in zip(rows[row], rows[column])
            ]
    return [rows[index][-1] for index in range(size)]


def _fit_no_intercept(xs: list[list[float]], ys: list[float]) -> list[float]:
    size = len(xs[0])
    matrix = [
        [sum(row[left] * row[right] for row in xs) for right in range(size)]
        for left in range(size)
    ]
    vector = [
        sum(row[column] * value for row, value in zip(xs, ys))
        for column in range(size)
    ]
    return _solve_linear(matrix, vector)


def _quantile(values: list[float], q: float) -> float:
    """Linear-interpolated quantile; q=0 and q=1 return the exact min and max."""
    ordered = sorted(values)
    position = q * (len(ordered) - 1)
    low = math.floor(position)
    high = math.ceil(position)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


@dataclass(frozen=True)
class FittedModel:
    summary_intercept: float
    summary_per_input: float
    summary_low_shift: float
    summary_high_shift: float
    seconds_per_uncached: float
    seconds_per_output: float
    output_speed: float
    time_r2: float
    output_only_r2: float
    input_only_r2: float
    central_cached_prefix: int
    low_cached_prefix: int
    high_cached_prefix: int


def fit_model(compactions: list[CompactionSample], profile: Profile) -> FittedModel:
    summary_points = [
        [1.0, float(item.input_tokens)]
        for item in compactions
    ]
    summary_values = [float(item.output_tokens) for item in compactions]
    summary_intercept, summary_per_input = _fit_no_intercept(
        summary_points,
        summary_values,
    )
    residuals = [
        item.output_tokens
        - (summary_intercept + summary_per_input * item.input_tokens)
        for item in compactions
    ]
    low_q, high_q = profile.range_quantiles

    def prefill_tokens(item: CompactionSample) -> float:
        if profile.prefill_time_on_total:
            return float(item.input_tokens)
        return float(item.input_tokens - item.cached_tokens)

    time_points = [
        [prefill_tokens(item), float(item.output_tokens)] for item in compactions
    ]
    time_values = [item.seconds for item in compactions]
    seconds_per_uncached, seconds_per_output = _fit_no_intercept(
        time_points,
        time_values,
    )

    def r2(features: list[list[float]]) -> float:
        coefficients = _fit_no_intercept(features, time_values)
        predictions = [
            sum(coefficient * value for coefficient, value in zip(coefficients, row))
            for row in features
        ]
        mean = statistics.fmean(time_values)
        return 1 - sum(
            (actual - predicted) ** 2
            for actual, predicted in zip(time_values, predictions)
        ) / sum((actual - mean) ** 2 for actual in time_values)

    # The cache parameter is the reusable cached prefix (fixed_prefix) or the
    # uncached tail of the compaction input (context_minus_tail). low_ is the
    # least cached scenario and high_ the most cached one.
    if profile.compaction_cache == "fixed_prefix":
        cache_values = [item.cached_tokens for item in compactions]
        low_cache_q, high_cache_q = low_q, high_q
    else:
        cache_values = [item.input_tokens - item.cached_tokens for item in compactions]
        low_cache_q, high_cache_q = high_q, low_q
    return FittedModel(
        summary_intercept=summary_intercept,
        summary_per_input=summary_per_input,
        summary_low_shift=_quantile(residuals, low_q),
        summary_high_shift=_quantile(residuals, high_q),
        seconds_per_uncached=seconds_per_uncached,
        seconds_per_output=seconds_per_output,
        output_speed=1 / seconds_per_output,
        time_r2=r2(time_points),
        output_only_r2=r2([[item.output_tokens] for item in compactions]),
        input_only_r2=r2([[prefill_tokens(item)] for item in compactions]),
        central_cached_prefix=round(statistics.median(cache_values)),
        low_cached_prefix=round(_quantile(cache_values, low_cache_q)),
        high_cached_prefix=round(_quantile(cache_values, high_cache_q)),
    )


def borrow_compactions(
    own: list[CompactionSample],
    donor: list[CompactionSample],
    profile: Profile,
) -> tuple[list[CompactionSample], float]:
    """Add another model's compactions to a model with too few of its own.

    The donor fit supplies how compaction time and summary size depend on the
    context. Donor durations are rescaled by the ratio of the model's own
    measured durations to what the donor fit predicts for them, so the level
    still comes from the model's own compactions. Returns the pooled compactions
    and the scale.
    """
    donor_model = fit_model(donor, profile)

    def predicted(item: CompactionSample) -> float:
        prefill = (
            item.input_tokens
            if profile.prefill_time_on_total
            else item.input_tokens - item.cached_tokens
        )
        return (
            donor_model.seconds_per_uncached * prefill
            + donor_model.seconds_per_output * item.output_tokens
        )

    scale = sum(item.seconds for item in own) / sum(predicted(item) for item in own)
    borrowed = [
        replace(
            item,
            name=f"borrowed-{item.name}",
            seconds=item.seconds * scale,
            source=f"borrowed-{item.source}",
        )
        for item in donor
    ]
    return own + borrowed, scale


def chain_requests(requests: list[Request], cuts: list[int]) -> list[Request]:
    """Join segments split by real compactions into one uncompacted request stream.

    `cuts` are the indexes of the first request after each real compaction.
    Each such segment is shifted so that its first request continues from the
    previous context by one typical increment with a typical uncached part.
    The replay then decides where compactions happen.
    """
    cut_set = {c for c in cuts if 0 < c < len(requests)}
    increments: list[int] = []
    uncached: list[int] = []
    for index in range(1, len(requests)):
        if index not in cut_set:
            increments.append(
                requests[index].input_tokens - requests[index - 1].input_tokens
            )
            uncached.append(
                requests[index].input_tokens - requests[index].cached_tokens
            )
    typical_increment = round(statistics.median(increments)) if increments else 0
    typical_uncached = round(statistics.median(uncached)) if uncached else 0

    chained: list[Request] = []
    offset = 0
    for index, request in enumerate(requests):
        if index in cut_set:
            context = chained[-1].input_tokens + max(0, typical_increment)
            offset = context - request.input_tokens
            chained.append(
                Request(
                    context,
                    context - min(context, typical_uncached),
                    request.output_tokens,
                )
            )
        else:
            chained.append(
                Request(
                    request.input_tokens + offset,
                    request.cached_tokens + offset,
                    request.output_tokens,
                )
            )
    return chained


def _summary_tokens(
    context: int,
    model: FittedModel,
    profile: Profile,
    shift: float = 0,
) -> int:
    estimate = (
        model.summary_intercept
        + model.summary_per_input * context
        + shift
    )
    return max(profile.min_summary, round(estimate))


def _replay_session(
    session: Session,
    threshold: int,
    model: FittedModel,
    profile: Profile,
    *,
    cached_prefix: int,
    summary_shift: float = 0,
) -> dict[str, float]:
    requests = session.requests
    mult = session.uncached_multiplier
    alpha = profile.alpha
    output_over_miss = profile.output_over_miss
    context = requests[0].input_tokens
    cost_units = 0.0
    compactions = 0
    prefill_seconds = 0.0
    output_seconds = 0.0

    for index, request in enumerate(requests):
        if index:
            context += request.input_tokens - requests[index - 1].input_tokens

        compacted = False
        if index and context > threshold:
            summary = _summary_tokens(context, model, profile, summary_shift)
            if profile.compaction_cache == "fixed_prefix":
                cached = min(context, cached_prefix)
            else:
                cached = max(0, context - cached_prefix)
            uncached = context - cached
            cost_units += (
                uncached * mult
                + alpha * cached
                + output_over_miss * summary
            )
            prefill_tokens = context if profile.prefill_time_on_total else uncached
            prefill_seconds += model.seconds_per_uncached * prefill_tokens
            output_seconds += model.seconds_per_output * summary
            compactions += 1
            context = profile.post_context
            compacted = True

        actual_uncached = request.input_tokens - request.cached_tokens
        uncached = (
            min(context, profile.post_cold_uncached)
            if compacted
            else min(context, actual_uncached)
        )
        cached = context - uncached
        cost_units += (
            uncached * mult
            + alpha * cached
            + output_over_miss * request.output_tokens
        )

    return {
        "cost_units": cost_units,
        "compactions": compactions,
        "prefill_seconds": prefill_seconds,
        "output_seconds": output_seconds,
        "compaction_seconds": prefill_seconds + output_seconds,
    }


def curve(
    sessions: list[Session],
    model: FittedModel,
    profile: Profile,
    *,
    cached_prefix: int,
    summary_shift: float = 0,
) -> list[dict]:
    work_seconds = sum(session.task_seconds for session in sessions)
    rows = []
    for threshold in range(
        profile.min_threshold,
        profile.max_threshold + 1,
        profile.threshold_step,
    ):
        results = [
            _replay_session(
                session,
                threshold,
                model,
                profile,
                cached_prefix=cached_prefix,
                summary_shift=summary_shift,
            )
            for session in sessions
        ]
        compaction_seconds = sum(
            result["compaction_seconds"] for result in results
        )
        time_share = compaction_seconds / (work_seconds + compaction_seconds)
        rows.append(
            {
                "threshold": threshold,
                "cost_usd_off_peak": (
                    sum(result["cost_units"] for result in results)
                    * profile.usd_per_token
                ),
                "compactions": sum(
                    result["compactions"] for result in results
                ),
                "compaction_seconds": compaction_seconds,
                "compaction_prefill_seconds": sum(
                    result["prefill_seconds"] for result in results
                ),
                "compaction_output_seconds": sum(
                    result["output_seconds"] for result in results
                ),
                "time_share": time_share,
                "feasible_time": time_share <= profile.time_limit,
            }
        )
    return rows


def scenario_curves(
    sessions: list[Session],
    model: FittedModel,
    profile: Profile,
) -> dict[str, list[dict]]:
    return {
        "central": curve(
            sessions,
            model,
            profile,
            cached_prefix=model.central_cached_prefix,
        ),
        "cost_low": curve(
            sessions,
            model,
            profile,
            cached_prefix=model.high_cached_prefix,
            summary_shift=model.summary_low_shift,
        ),
        "cost_high": curve(
            sessions,
            model,
            profile,
            cached_prefix=model.low_cached_prefix,
            summary_shift=model.summary_high_shift,
        ),
    }


def _resample_session(session: Session, rng: random.Random, block_size: int) -> Session:
    requests = session.requests
    if len(requests) < 2:
        return Session(
            list(requests),
            session.task_seconds,
            session.segment,
            session.uncached_multiplier,
        )

    transitions = [
        (
            current.input_tokens - previous.input_tokens,
            current.input_tokens - current.cached_tokens,
            current.output_tokens,
        )
        for previous, current in zip(requests, requests[1:])
    ]
    picked: list[tuple[int, int, int]] = []
    while len(picked) < len(transitions):
        start = rng.randrange(len(transitions))
        picked.extend(
            transitions[(start + offset) % len(transitions)]
            for offset in range(block_size)
        )
    picked = picked[: len(transitions)]

    context = requests[0].input_tokens
    initial_uncached = max(
        0,
        min(context, requests[0].input_tokens - requests[0].cached_tokens),
    )
    sampled = [
        Request(
            input_tokens=context,
            cached_tokens=context - initial_uncached,
            output_tokens=requests[0].output_tokens,
        )
    ]
    for increment, uncached, output_tokens in picked:
        context = max(0, context + increment)
        actual_uncached = max(0, min(context, uncached))
        sampled.append(
            Request(
                input_tokens=context,
                cached_tokens=context - actual_uncached,
                output_tokens=output_tokens,
            )
        )
    return Session(
        sampled,
        session.task_seconds,
        session.segment,
        session.uncached_multiplier,
    )


@dataclass(frozen=True)
class _WorkerJob:
    sessions: list[Session]
    model: FittedModel
    profile: Profile
    config: BootstrapConfig


_WORKER_JOB: _WorkerJob | None = None


def _init_worker(job: _WorkerJob) -> None:
    global _WORKER_JOB
    _WORKER_JOB = job


def _bootstrap_replicate(index: int) -> dict[str, list[dict]]:
    if _WORKER_JOB is None:
        raise RuntimeError("Bootstrap worker was not initialized")
    job = _WORKER_JOB
    rng = random.Random(job.config.seed + index)
    sessions = [
        _resample_session(session, rng, job.config.block_requests)
        for session in job.sessions
    ]
    return scenario_curves(sessions, job.model, job.profile)


def _average_curves(
    replicates: list[dict[str, list[dict]]],
    sessions: list[Session],
    profile: Profile,
) -> dict[str, list[dict]]:
    work_seconds = sum(session.task_seconds for session in sessions)
    output = {}
    for name in ("central", "cost_low", "cost_high"):
        replicate_curves = [replicate[name] for replicate in replicates]
        rows = []
        for index, base in enumerate(replicate_curves[0]):
            compaction_seconds = statistics.fmean(
                rows[index]["compaction_seconds"] for rows in replicate_curves
            )
            time_share = compaction_seconds / (work_seconds + compaction_seconds)
            cost = statistics.fmean(
                rows[index]["cost_usd_off_peak"] for rows in replicate_curves
            )
            rows.append(
                {
                    "threshold": base["threshold"],
                    "cost_usd_off_peak": cost,
                    "compactions": statistics.fmean(
                        rows[index]["compactions"] for rows in replicate_curves
                    ),
                    "compaction_seconds": compaction_seconds,
                    "compaction_prefill_seconds": statistics.fmean(
                        rows[index]["compaction_prefill_seconds"]
                        for rows in replicate_curves
                    ),
                    "compaction_output_seconds": statistics.fmean(
                        rows[index]["compaction_output_seconds"]
                        for rows in replicate_curves
                    ),
                    "time_share": time_share,
                    "feasible_time": time_share <= profile.time_limit,
                }
            )
        output[name] = rows
    return output


def bootstrap_curves(
    sessions: list[Session],
    model: FittedModel,
    profile: Profile,
    config: BootstrapConfig,
) -> dict[str, list[dict]]:
    job = _WorkerJob(sessions, model, profile, config)
    indices = range(config.replicates)
    if config.workers <= 1:
        _init_worker(job)
        replicates = [_bootstrap_replicate(index) for index in indices]
    else:
        with Pool(
            processes=config.workers,
            initializer=_init_worker,
            initargs=(job,),
        ) as pool:
            replicates = list(pool.imap(_bootstrap_replicate, indices, chunksize=1))
    return _average_curves(replicates, sessions, profile)


def _minimum_valid(rows: list[dict]) -> dict:
    return min(
        (row for row in rows if row["feasible_time"]),
        key=lambda row: row["cost_usd_off_peak"],
    )


def _compact_curve(rows: list[dict]) -> list[dict]:
    fields = (
        "threshold",
        "cost_usd_off_peak",
        "compactions",
        "compaction_seconds",
        "compaction_prefill_seconds",
        "compaction_output_seconds",
        "time_share",
        "feasible_time",
        "cost_per_million_tokens",
    )
    return [{field: row[field] for field in fields} for row in rows]


def build_result(
    sessions: list[Session],
    excluded_count: dict[str, int],
    compactions: list[CompactionSample],
    profile: Profile,
    config: BootstrapConfig,
    billing_mix: dict[str, int],
    extra_snapshot: dict | None = None,
) -> dict:
    model = fit_model(compactions, profile)
    exact_curves = scenario_curves(sessions, model, profile)
    curves = bootstrap_curves(sessions, model, profile, config)

    # Cost per 1M billed tokens: one constant per profile, the billed tokens
    # of the real history (not of each replay, which changes with the threshold).
    billed_tokens = sum(billing_mix.values())
    for rows in (*curves.values(), *exact_curves.values()):
        for row in rows:
            row["cost_per_million_tokens"] = (
                row["cost_usd_off_peak"] * 1_000_000 / billed_tokens
            )

    scenarios = {}
    for name, rows in curves.items():
        scenarios[name] = {
            "cost_optimum": _minimum_valid(rows),
            "time_feasible_from": next(
                (row["threshold"] for row in rows if row["feasible_time"]),
                None,
            ),
            "baseline_900k": rows[-1],
        }

    included_active_tail = any(
        session.segment == "active-post-compaction" for session in sessions
    )
    increments = [
        current.input_tokens - previous.input_tokens
        for session in sessions
        for previous, current in zip(session.requests, session.requests[1:])
    ]
    measurements = [
        {
            "name": item.name,
            "source": item.source,
            "input": item.input_tokens,
            "cached": item.cached_tokens,
            "output": item.output_tokens,
            "seconds": item.seconds,
            "cache_fraction": item.cached_tokens / item.input_tokens,
            "cost_usd_off_peak": (
                (item.input_tokens - item.cached_tokens)
                * profile.write_multiplier
                + profile.alpha * item.cached_tokens
                + profile.output_over_miss * item.output_tokens
            )
            * profile.usd_per_token,
        }
        for item in compactions
    ]

    result = {
        "snapshot": {
            "model": profile.model,
            "max_context_window": profile.context_window,
            "max_threshold": profile.max_threshold,
            "reliability_floor": profile.min_threshold,
            "time_limit": profile.time_limit,
            "off_peak_miss_usd_per_million": profile.prices["input"],
            "off_peak_cached_usd_per_million": profile.prices["cache_read"],
            "off_peak_output_usd_per_million": profile.prices["output"],
            "alpha": profile.alpha,
            "output_over_miss": profile.output_over_miss,
            "requests": sum(len(session.requests) for session in sessions),
            "billed_tokens": billed_tokens,
            "billing_mix": billing_mix,
            "work_seconds": sum(session.task_seconds for session in sessions),
            "included_sessions": len(sessions) - int(included_active_tail),
            "included_active_tail": included_active_tail,
            "max_input_tokens": max(
                request.input_tokens
                for session in sessions
                for request in session.requests
            ),
            "mean_increment": statistics.fmean(increments),
            "excluded": excluded_count,
            "analysis_mode": "block-bootstrap-from-real-session-transitions",
        },
        "fitted_model": {
            "summary_tokens_intercept": model.summary_intercept,
            "summary_tokens_per_compaction_input": model.summary_per_input,
            "summary_residual_low_shift": model.summary_low_shift,
            "summary_residual_high_shift": model.summary_high_shift,
            "seconds_per_uncached_input": model.seconds_per_uncached,
            "seconds_per_billed_output": model.seconds_per_output,
            "output_speed_tokens_per_second": model.output_speed,
            "time_r2_two_factor": model.time_r2,
            "time_r2_output_only": model.output_only_r2,
            "time_r2_input_only": model.input_only_r2,
            "central_cached_prefix_tokens": model.central_cached_prefix,
            "low_cached_prefix_tokens": model.low_cached_prefix,
            "high_cached_prefix_tokens": model.high_cached_prefix,
            "post_compaction_context": profile.post_context,
            "post_compaction_cold_uncached": profile.post_cold_uncached,
            "bootstrap_replicates": config.replicates,
            "bootstrap_block_requests": config.block_requests,
            "bootstrap_seed": config.seed,
        },
        "measurements": measurements,
        "curves": curves,
        "exact_curves": {
            name: _compact_curve(rows)
            for name, rows in exact_curves.items()
        },
        "scenario_results": scenarios,
        "central_curve": _compact_curve(curves["central"]),
        "exact_central_curve": _compact_curve(exact_curves["central"]),
    }
    result["snapshot"].update(extra_snapshot or {})
    return result
