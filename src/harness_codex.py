"""Codex harness: load model workloads from Codex session JSONL logs."""

from __future__ import annotations

import json
import statistics
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

from analysis import (
    CompactionSample,
    Collected,
    Request,
    Session,
    chain_requests,
    fill_unknown_seconds,
    parse_timestamp,
)
from model_profile import Profile


# Marks a real compaction in the request list from _read_session.
COMPACTION = (None, None)

# response_item types that are the model's own output; every other response
# item (user and developer messages, tool outputs) is input of the next request.
MODEL_OUTPUT = {"reasoning", "function_call", "custom_tool_call", "tool_search_call"}

# A token_count this close to the compaction record belongs to the compaction
# request itself, not to the request before it.
COMPACTION_OWN_EVENT_SECONDS = 1.0


def _session_start(path: Path) -> float | None:
    """Read the recorded start, never the file's modification time."""
    with path.open("rb") as stream:
        for line in stream:
            try:
                record = json.loads(line)
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
            if isinstance(record, dict) and record.get("type") == "session_meta":
                value = (record.get("payload") or {}).get("timestamp") or record.get(
                    "timestamp"
                )
                return parse_timestamp(value) if value else None
    return None


@dataclass
class _Log:
    found: bool = False
    other_model: bool = False
    meta: dict = field(default_factory=dict)
    # Requests in order (response id, request), with a COMPACTION marker where
    # Codex compacted.
    requests: list = field(default_factory=list)
    # Real compactions as (compaction response id, sample).
    compactions: list = field(default_factory=list)


def _read_session(path: Path, profile: Profile) -> _Log:
    """Requests, request durations and real compactions of one session.

    Codex logs the compaction request just before its `compacted` record. It is
    removed from the request list (the replay models compactions itself) and
    kept as a compaction sample.
    """
    log = _Log()
    models: set[str] = set()
    token_counts: list[float] = []
    request_start: float | None = None
    turn_start: float | None = None
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
                log.meta = payload
            elif event_type == "turn_context" and payload.get("model"):
                models.add(payload["model"])
            elif event_type == "response_item" and not (
                subtype in MODEL_OUTPUT
                or (subtype == "message" and payload.get("role") == "assistant")
            ):
                request_start = parse_timestamp(record["timestamp"])
            elif event_type == "event_msg" and subtype == "token_count":
                token_counts.append(parse_timestamp(record["timestamp"]))
            elif event_type == "event_msg" and subtype == "task_started":
                turn_start = parse_timestamp(record["timestamp"])
            elif event_type == "compacted":
                now = parse_timestamp(record["timestamp"])
                if log.requests and log.requests[-1] is not COMPACTION:
                    _, request = log.requests.pop()
                    log.requests.append(COMPACTION)
                    start = next(
                        (
                            t
                            for t in reversed(token_counts)
                            if t < now - COMPACTION_OWN_EVENT_SECONDS
                        ),
                        None,
                    )
                    # A new turn may compact before its first ordinary request.
                    # The previous token_count can then predate the user's wait.
                    if turn_start is not None:
                        start = max(start, turn_start) if start is not None else turn_start
                    if start is not None:
                        log.compactions.append(
                            (
                                payload.get("compaction_response_id"),
                                CompactionSample(
                                    name="",
                                    input_tokens=request.input_tokens,
                                    cached_tokens=request.cached_tokens,
                                    output_tokens=request.output_tokens,
                                    seconds=now - start,
                                    source="log-auto",
                                ),
                            )
                        )
                # The request after a compaction starts when the compaction ends.
                request_start = now
            elif event_type == "token_usage_record":
                usage = payload.get("usage") or {}
                if usage.get("input_tokens") is None:
                    continue
                end = parse_timestamp(record["timestamp"])
                log.requests.append(
                    (
                        payload.get("response_id"),
                        Request(
                            input_tokens=int(usage["input_tokens"]),
                            cached_tokens=int(usage.get("cached_input_tokens") or 0),
                            output_tokens=int(usage.get("output_tokens") or 0),
                            seconds=(
                                end - request_start if request_start is not None else 0.0
                            ),
                        ),
                    )
                )
                request_start = None
    log.found = (
        profile.provider is not None
        and log.meta.get("model_provider") == profile.provider
    ) or any(model.startswith(profile.model_prefixes) for model in models)
    log.other_model = any(
        not model.startswith(profile.model_prefixes) for model in models
    )
    return log


def collect(
    session_root: Path,
    profile: Profile,
    *,
    active_thread: str | None = None,
    excluded_threads: Iterable[str] = (),
    snapshot_at: datetime | None = None,
) -> Collected:
    """Load Codex workloads without exposing raw sessions in output."""
    excluded = set(excluded_threads)
    seen_responses: set[str] = set()
    seen_compactions: set[str] = set()
    sessions: list[Session] = []
    compactions: list[CompactionSample] = []
    # Requests as logged (not chained), for the billing mix.
    raw: list[Request] = []
    excluded_count: Counter[str] = Counter()
    post_requests: list[Request] = []
    selection = None
    if profile.session_max_age_days is not None:
        end = snapshot_at or datetime.now(timezone.utc)
        start = end - timedelta(days=profile.session_max_age_days)
        selection = {
            "max_age_days": profile.session_max_age_days,
            "started_at_or_after": start.isoformat(),
            "started_at_or_before": end.isoformat(),
        }

    for path in sorted(session_root.rglob("*.jsonl")):
        # Filter whole sessions before they can consume response IDs or supply
        # compaction calibration, including old sessions resumed recently.
        if selection is not None:
            started = _session_start(path)
            if started is None:
                excluded_count["session-start-unknown"] += 1
                continue
            if not start.timestamp() <= started <= end.timestamp():
                excluded_count["session-start-outside-window"] += 1
                continue
        log = _read_session(path, profile)
        if not log.found:
            continue
        meta = log.meta
        thread = meta.get("id")
        parent = meta.get("parent_thread_id")
        cwd = meta.get("cwd") or ""

        unique: list[Request] = []
        cuts: list[int] = []
        for response_id, request in log.requests:
            if request is None:
                cuts.append(len(unique))
                continue
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
        elif any(part in cwd for part in profile.harness_cfg["excluded_cwd_markers"]):
            reason = "smoke-or-test"
        elif log.other_model:
            # Matched by provider, but a session on another model (other prices).
            reason = "other-model"
        elif not unique:
            reason = "empty"

        # Compactions of the analysis session count; the calibration sessions
        # are the hand-measured samples already in the compactions file.
        if reason in (None, "active-analysis"):
            post_requests.extend(unique[cut] for cut in cuts if cut < len(unique))
            for response_id, sample in log.compactions:
                if response_id is None or response_id not in seen_compactions:
                    seen_compactions.add(response_id)
                    compactions.append(sample)
        if reason == "active-analysis" and thread == active_thread and cuts:
            # Its latest stretch after the last compaction is part of the workload.
            tail = unique[cuts[-1] :]
            if tail:
                raw.extend(tail)
                sessions.append(Session(tail, segment="active-post-compaction"))
        if reason is not None:
            excluded_count[reason] += 1
            continue
        raw.extend(unique)
        sessions.append(Session(chain_requests(unique, cuts)))

    if not sessions:
        raise ValueError(f"No {profile.model} sessions with token usage were found")
    if profile.post_context is None or profile.post_cold_uncached is None:
        if not post_requests:
            raise ValueError(f"No post-compaction requests found for {profile.model}")
        profile = profile.with_measured(
            round(statistics.median(r.input_tokens for r in post_requests)),
            round(statistics.median(r.input_tokens - r.cached_tokens for r in post_requests)),
        )
    compactions = [
        CompactionSample(
            f"log-{number:03d}",
            item.input_tokens,
            item.cached_tokens,
            item.output_tokens,
            item.seconds,
            item.source,
        )
        for number, item in enumerate(compactions, 1)
    ]
    unknown = fill_unknown_seconds(sessions)
    billing_mix = {
        "uncached_input": sum(r.input_tokens - r.cached_tokens for r in raw),
        "cache_write_5m": 0,
        "cache_write_1h": 0,
        "cache_read": sum(r.cached_tokens for r in raw),
        "output": sum(r.output_tokens for r in raw),
    }
    stats = {
        "max_input_tokens": max(r.input_tokens for r in raw),
        "requests_without_duration": unknown,
    }
    if selection is not None:
        stats["session_selection"] = selection
    return Collected(
        sessions, dict(excluded_count), compactions, profile, stats, billing_mix
    )
