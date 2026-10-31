"""Codex harness: load model workloads from Codex session JSONL logs."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Iterable

from analysis import Collected, Request, Session, chain_requests, parse_timestamp
from model_profile import Profile


# Marks a real compaction in the request list from _read_session.
COMPACTION = (None, None)


def _read_session(path: Path, profile: Profile) -> tuple[
    bool,
    dict,
    list[tuple[str | None, Request | None]],
    float,
    bool,
]:
    """Requests in order, with a COMPACTION marker where Codex compacted.

    Codex logs the compaction request just before its `compacted` record. It is
    removed here: the replay models compactions itself.
    """
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
            if event_type == "compacted":
                if requests and requests[-1] is not COMPACTION:
                    requests.pop()
                    requests.append(COMPACTION)
                continue
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
    found = (
        profile.provider is not None
        and meta.get("model_provider") == profile.provider
    ) or any(model.startswith(profile.model_prefixes) for model in models)
    other_model = any(not model.startswith(profile.model_prefixes) for model in models)
    return found, meta, requests, task_ms / 1_000, other_model


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
                open_task_started = parse_timestamp(record["timestamp"])
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
            last_request_time = parse_timestamp(record["timestamp"])
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


def collect(
    session_root: Path,
    profile: Profile,
    *,
    active_thread: str | None = None,
    excluded_threads: Iterable[str] = (),
) -> Collected:
    """Load Codex workloads without exposing raw sessions in output."""
    excluded = set(excluded_threads)
    seen_responses: set[str] = set()
    sessions: list[Session] = []
    # Requests as logged (not chained), for the billing mix.
    raw: list[Request] = []
    excluded_count: Counter[str] = Counter()

    for path in sorted(session_root.rglob("*.jsonl")):
        found, meta, records, task_seconds, other_model = _read_session(path, profile)
        if not found:
            continue
        thread = meta.get("id")
        parent = meta.get("parent_thread_id")
        cwd = meta.get("cwd") or ""

        unique: list[Request] = []
        cuts: list[int] = []
        for response_id, request in records:
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
        elif other_model:
            # Matched by provider, but a session on another model (other prices).
            reason = "other-model"
        elif not unique:
            reason = "empty"

        if reason is not None:
            excluded_count[reason] += 1
            continue
        raw.extend(unique)
        sessions.append(
            Session(requests=chain_requests(unique, cuts), task_seconds=task_seconds)
        )

    if active_thread:
        matches = sorted(session_root.rglob(f"*{active_thread}.jsonl"))
        if matches:
            tail = _read_active_tail(matches[-1])
            if tail is not None:
                raw.extend(tail.requests)
                sessions.append(tail)

    if not sessions:
        raise ValueError(f"No {profile.model} sessions with token usage were found")
    # Codex logs carry no usable compaction timings: calibration comes from
    # the profile's trials file.
    billing_mix = {
        "uncached_input": sum(r.input_tokens - r.cached_tokens for r in raw),
        "cache_write_5m": 0,
        "cache_write_1h": 0,
        "cache_read": sum(r.cached_tokens for r in raw),
        "output": sum(r.output_tokens for r in raw),
    }
    stats = {"max_input_tokens": max(r.input_tokens for r in raw)}
    return Collected(
        sessions, dict(excluded_count), None, profile, stats, billing_mix
    )
