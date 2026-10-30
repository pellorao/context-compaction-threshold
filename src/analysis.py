"""Analyze DeepSeek compaction thresholds from local Codex session logs."""

from __future__ import annotations

import json
import math
import os
import random
import statistics
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from multiprocessing import Pool
from pathlib import Path
from typing import Iterable


MODEL = "deepseek-flash"
CONTEXT_WINDOW = 996_147
MAX_THRESHOLD = 900_000
MIN_THRESHOLD = 64_000
THRESHOLD_STEP = 2_000
TIME_LIMIT = 0.05

ALPHA = 0.02
OUTPUT_OVER_MISS = 4.0
OFF_PEAK_MISS_PER_TOKEN = 0.15 / 1_000_000

POST_COMPACTION_CONTEXT = 17_623
POST_COMPACTION_COLD_UNCACHED = 13_152
MIN_SUMMARY = 1_000


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


@dataclass(frozen=True)
class Trial:
    name: str
    input_tokens: int
    cached_tokens: int
    output_tokens: int
    seconds: float
    source: str


@dataclass(frozen=True)
class BootstrapConfig:
    replicates: int = 100
    block_requests: int = 8
    seed: int = 20_261_031
    workers: int = min(8, os.cpu_count() or 1)


def _timestamp(value: str) -> float:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def _read_session(path: Path) -> tuple[
    bool,
    dict,
    list[tuple[str | None, Request]],
    float,
]:
    meta: dict = {}
    models: set[str] = set()
    requests: list[tuple[str | None, Request]] = []
    task_ms = 0
    # Read bytes: Python 3.14's incremental text reader intermittently
    # segfaults on some very long third-party JSONL records.
    with path.open("rb") as stream:
        for line in stream:
            try:
                record = json.loads(line)
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
            if not isinstance(record, dict):
                continue
            payload = record.get("payload") or {}
            event_type = record.get("type")
            subtype = payload.get("type")
            if event_type == "session_meta":
                meta = payload
            elif event_type == "turn_context" and payload.get("model"):
                models.add(payload["model"])
            if event_type == "event_msg" and subtype == "task_complete":
                task_ms += int(payload.get("duration_ms") or 0)
            if event_type != "token_usage_record":
                continue
            usage = payload.get("usage") or {}
            if usage.get("input_tokens") is None:
                continue
            requests.append(
                (
                    payload.get("response_id"),
                    Request(
                        input_tokens=int(usage["input_tokens"]),
                        cached_tokens=int(
                            usage.get("cached_input_tokens") or 0
                        ),
                        output_tokens=int(usage.get("output_tokens") or 0),
                    ),
                )
            )
    found = meta.get("model_provider") == "deepseek" or MODEL in models
    return found, meta, requests, task_ms / 1_000


def _read_active_tail(path: Path) -> Session | None:
    requests: list[Request] = []
    task_ms = 0
    in_tail = False
    skip_compaction_complete = False
    open_task_started: float | None = None
    last_request_time: float | None = None

    with path.open("rb") as stream:
        for line in stream:
            try:
                record = json.loads(line)
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
            if not isinstance(record, dict):
                continue
            payload = record.get("payload") or {}
            event_type = record.get("type")
            subtype = payload.get("type")
            if event_type == "compacted":
                requests = []
                task_ms = 0
                in_tail = True
                skip_compaction_complete = True
                open_task_started = None
                last_request_time = None
                continue
            if not in_tail:
                continue
            if event_type == "event_msg" and subtype == "task_started":
                open_task_started = _timestamp(record["timestamp"])
                continue
            if event_type == "event_msg" and subtype == "task_complete":
                if skip_compaction_complete:
                    skip_compaction_complete = False
                else:
                    task_ms += int(payload.get("duration_ms") or 0)
                open_task_started = None
                continue
            if event_type != "token_usage_record":
                continue
            usage = payload.get("usage") or {}
            if usage.get("input_tokens") is None:
                continue
            last_request_time = _timestamp(record["timestamp"])
            requests.append(
                Request(
                    input_tokens=int(usage["input_tokens"]),
                    cached_tokens=int(usage.get("cached_input_tokens") or 0),
                    output_tokens=int(usage.get("output_tokens") or 0),
                )
            )

    if not requests:
        return None
    if open_task_started is not None and last_request_time is not None:
        task_ms += max(0, round((last_request_time - open_task_started) * 1_000))
    return Session(
        requests=requests,
        task_seconds=task_ms / 1_000,
        segment="active-post-compaction",
    )


def load_workload(
    session_root: Path,
    *,
    active_thread: str | None = None,
    excluded_threads: Iterable[str] = (),
) -> tuple[list[Session], dict[str, int]]:
    """Load DeepSeek workloads without exposing raw sessions in output."""
    excluded = set(excluded_threads)
    seen_responses: set[str] = set()
    sessions: list[Session] = []
    excluded_count: Counter[str] = Counter()

    for path in sorted(session_root.rglob("*.jsonl")):
        found, meta, records, task_seconds = _read_session(path)
        if not found:
            continue
        thread = meta.get("id")
        parent = meta.get("parent_thread_id")
        cwd = meta.get("cwd") or ""

        unique: list[Request] = []
        for response_id, request in records:
            if response_id in seen_responses:
                continue
            if response_id:
                seen_responses.add(response_id)
            unique.append(request)

        reason = None
        if active_thread and (thread == active_thread or parent == active_thread):
            reason = "active-analysis"
        elif thread in excluded or parent in excluded:
            reason = "compaction-calibration"
        elif any(part in cwd for part in ("smoke", "probe", "test")):
            reason = "smoke-or-test"
        elif not unique:
            reason = "empty"

        if reason is not None:
            excluded_count[reason] += 1
            continue
        sessions.append(Session(requests=unique, task_seconds=task_seconds))

    if active_thread:
        matches = sorted(session_root.rglob(f"*{active_thread}.jsonl"))
        if matches:
            tail = _read_active_tail(matches[-1])
            if tail is not None:
                sessions.append(tail)

    if not sessions:
        raise ValueError("No DeepSeek sessions with token usage were found")
    return sessions, dict(excluded_count)


def load_trials(path: Path) -> list[Trial]:
    raw = json.loads(path.read_text())
    return [
        Trial(
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


def fit_model(trials: list[Trial]) -> FittedModel:
    summary_points = [
        [1.0, float(item.input_tokens)]
        for item in trials
    ]
    summary_values = [float(item.output_tokens) for item in trials]
    summary_intercept, summary_per_input = _fit_no_intercept(
        summary_points,
        summary_values,
    )
    residuals = [
        item.output_tokens
        - (summary_intercept + summary_per_input * item.input_tokens)
        for item in trials
    ]

    time_points = [
        [
            float(item.input_tokens - item.cached_tokens),
            float(item.output_tokens),
        ]
        for item in trials
    ]
    time_values = [item.seconds for item in trials]
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

    cached_prefixes = [item.cached_tokens for item in trials]
    return FittedModel(
        summary_intercept=summary_intercept,
        summary_per_input=summary_per_input,
        summary_low_shift=min(residuals),
        summary_high_shift=max(residuals),
        seconds_per_uncached=seconds_per_uncached,
        seconds_per_output=seconds_per_output,
        output_speed=1 / seconds_per_output,
        time_r2=r2(time_points),
        output_only_r2=r2([[item.output_tokens] for item in trials]),
        input_only_r2=r2(
            [[item.input_tokens - item.cached_tokens] for item in trials]
        ),
        central_cached_prefix=round(statistics.median(cached_prefixes)),
        low_cached_prefix=min(cached_prefixes),
        high_cached_prefix=max(cached_prefixes),
    )


def _summary_tokens(context: int, model: FittedModel, shift: float = 0) -> int:
    estimate = (
        model.summary_intercept
        + model.summary_per_input * context
        + shift
    )
    return max(MIN_SUMMARY, round(estimate))


def _replay_session(
    session: Session,
    threshold: int,
    model: FittedModel,
    *,
    cached_prefix: int,
    summary_shift: float = 0,
) -> dict[str, float]:
    requests = session.requests
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
            summary = _summary_tokens(context, model, summary_shift)
            cached = min(context, cached_prefix)
            uncached = context - cached
            cost_units += (
                uncached
                + ALPHA * cached
                + OUTPUT_OVER_MISS * summary
            )
            prefill_seconds += model.seconds_per_uncached * uncached
            output_seconds += model.seconds_per_output * summary
            compactions += 1
            context = POST_COMPACTION_CONTEXT
            compacted = True

        actual_uncached = request.input_tokens - request.cached_tokens
        uncached = (
            min(context, POST_COMPACTION_COLD_UNCACHED)
            if compacted
            else min(context, actual_uncached)
        )
        cached = context - uncached
        cost_units += (
            uncached
            + ALPHA * cached
            + OUTPUT_OVER_MISS * request.output_tokens
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
    *,
    cached_prefix: int,
    summary_shift: float = 0,
) -> list[dict]:
    work_seconds = sum(session.task_seconds for session in sessions)
    rows = []
    for threshold in range(MIN_THRESHOLD, MAX_THRESHOLD + 1, THRESHOLD_STEP):
        results = [
            _replay_session(
                session,
                threshold,
                model,
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
                    * OFF_PEAK_MISS_PER_TOKEN
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
                "feasible_time": time_share <= TIME_LIMIT,
            }
        )
    return rows


def _resample_session(session: Session, rng: random.Random, block_size: int) -> Session:
    requests = session.requests
    if len(requests) < 2:
        return Session(list(requests), session.task_seconds, session.segment)

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
    return Session(sampled, session.task_seconds, session.segment)


@dataclass(frozen=True)
class _WorkerJob:
    sessions: list[Session]
    model: FittedModel
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
    return {
        "central": curve(
            sessions,
            job.model,
            cached_prefix=job.model.central_cached_prefix,
        ),
        "cost_low": curve(
            sessions,
            job.model,
            cached_prefix=job.model.high_cached_prefix,
            summary_shift=job.model.summary_low_shift,
        ),
        "cost_high": curve(
            sessions,
            job.model,
            cached_prefix=job.model.low_cached_prefix,
            summary_shift=job.model.summary_high_shift,
        ),
    }


def _average_curves(
    replicates: list[dict[str, list[dict]]],
    sessions: list[Session],
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
                    "feasible_time": time_share <= TIME_LIMIT,
                }
            )
        output[name] = rows
    return output


def bootstrap_curves(
    sessions: list[Session],
    model: FittedModel,
    config: BootstrapConfig,
) -> dict[str, list[dict]]:
    job = _WorkerJob(sessions, model, config)
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
    return _average_curves(replicates, sessions)


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
    )
    return [{field: row[field] for field in fields} for row in rows]


def build_result(
    sessions: list[Session],
    excluded_count: dict[str, int],
    trials: list[Trial],
    config: BootstrapConfig,
) -> dict:
    model = fit_model(trials)
    exact_curves = {
        "central": curve(
            sessions,
            model,
            cached_prefix=model.central_cached_prefix,
        ),
        "cost_low": curve(
            sessions,
            model,
            cached_prefix=model.high_cached_prefix,
            summary_shift=model.summary_low_shift,
        ),
        "cost_high": curve(
            sessions,
            model,
            cached_prefix=model.low_cached_prefix,
            summary_shift=model.summary_high_shift,
        ),
    }
    curves = bootstrap_curves(sessions, model, config)

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
                item.input_tokens
                - item.cached_tokens
                + ALPHA * item.cached_tokens
                + OUTPUT_OVER_MISS * item.output_tokens
            )
            * OFF_PEAK_MISS_PER_TOKEN,
        }
        for item in trials
    ]

    return {
        "snapshot": {
            "model": MODEL,
            "max_context_window": CONTEXT_WINDOW,
            "max_threshold": MAX_THRESHOLD,
            "reliability_floor": MIN_THRESHOLD,
            "time_limit": TIME_LIMIT,
            "off_peak_miss_usd_per_million": 0.15,
            "off_peak_cached_usd_per_million": 0.003,
            "off_peak_output_usd_per_million": 0.60,
            "alpha": ALPHA,
            "output_over_miss": OUTPUT_OVER_MISS,
            "requests": sum(len(session.requests) for session in sessions),
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
            "post_compaction_context": POST_COMPACTION_CONTEXT,
            "post_compaction_cold_uncached": POST_COMPACTION_COLD_UNCACHED,
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
