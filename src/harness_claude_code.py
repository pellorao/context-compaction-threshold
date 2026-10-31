"""Claude Code harness: load model workloads from Claude Code transcripts.

Raw transcripts are only read; nothing derived from them keeps session ids,
paths, prompts or message content.
"""

from __future__ import annotations

import json
import statistics
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from analysis import (
    Collected,
    Request,
    Session,
    CompactionSample,
    _fit_no_intercept,
    chain_requests,
    parse_timestamp,
)
from model_profile import Profile


CJK_FROM = 0x2E80
CALIBRATION_MIN_CHARS = 200


@dataclass
class _Message:
    model: str
    timestamp: float
    input_tokens: int
    written_5m: int
    written_1h: int
    cache_read: int
    output_tokens: int
    thinking_tokens: int
    text_cjk: int = 0
    text_other: int = 0
    text_only: bool = True
    stop_reason: str | None = None

    @property
    def context(self) -> int:
        return (
            self.input_tokens + self.written_5m + self.written_1h + self.cache_read
        )


@dataclass
class _Boundary:
    """A compact_boundary entry plus the request count before it."""

    position: int
    timestamp: float
    trigger: str
    pre_tokens: int
    duration_seconds: float
    summary_cjk: int | None = None
    summary_other: int | None = None


@dataclass
class _Transcript:
    subagent: bool
    messages: list[_Message] = field(default_factory=list)
    boundaries: list[_Boundary] = field(default_factory=list)


def _char_classes(text: str) -> tuple[int, int]:
    cjk = sum(1 for char in text if ord(char) > CJK_FROM)
    return cjk, len(text) - cjk


def _read_transcript(
    path: Path,
    seen_messages: set[str],
    seen_boundaries: set[tuple[float, int]],
    model_prefixes: tuple[str, ...],
) -> _Transcript:
    """Parse one transcript; messages are unique across files by message id."""
    transcript = _Transcript(subagent="subagents" in path.parts)
    by_id: dict[str, _Message] = {}
    skipped_ids: set[str] = set()
    # Read bytes: Python 3.14's incremental text reader intermittently
    # segfaults on some very long third-party JSONL records.
    with path.open("rb") as stream:
        for line in stream:
            if b'"type":"assistant"' in line:
                kind = "assistant"
            elif b'"subtype":"compact_boundary"' in line:
                kind = "boundary"
            elif b'"isCompactSummary":true' in line:
                kind = "summary"
            else:
                continue
            try:
                record = json.loads(line)
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
            if not isinstance(record, dict):
                continue
            if kind == "assistant":
                message = record.get("message") or {}
                usage = message.get("usage") or {}
                message_id = message.get("id")
                model = message.get("model") or ""
                if (
                    not message_id
                    or message_id in skipped_ids
                    or not model.startswith(model_prefixes)
                ):
                    continue
                parsed = by_id.get(message_id)
                if parsed is None:
                    if message_id in seen_messages:
                        skipped_ids.add(message_id)
                        continue
                    created = usage.get("cache_creation") or {}
                    total_written = usage.get("cache_creation_input_tokens") or 0
                    # Without a TTL breakdown, assume the 1-hour TTL.
                    written_5m = created.get("ephemeral_5m_input_tokens") or 0
                    written_1h = (
                        created.get("ephemeral_1h_input_tokens")
                        if created
                        else total_written
                    ) or 0
                    parsed = _Message(
                        model=model,
                        timestamp=parse_timestamp(record["timestamp"]),
                        input_tokens=usage.get("input_tokens") or 0,
                        written_5m=written_5m,
                        written_1h=written_1h,
                        cache_read=usage.get("cache_read_input_tokens") or 0,
                        output_tokens=0,
                        thinking_tokens=0,
                    )
                    by_id[message_id] = parsed
                    seen_messages.add(message_id)
                    transcript.messages.append(parsed)
                # One response is split over several lines; later lines carry
                # the final output count.
                output = usage.get("output_tokens") or 0
                if output >= parsed.output_tokens:
                    parsed.output_tokens = output
                    parsed.thinking_tokens = (
                        usage.get("output_tokens_details") or {}
                    ).get("thinking_tokens") or 0
                parsed.stop_reason = message.get("stop_reason") or parsed.stop_reason
                content = message.get("content")
                for block in content if isinstance(content, list) else ():
                    if block.get("type") == "text":
                        cjk, other = _char_classes(block.get("text") or "")
                        parsed.text_cjk += cjk
                        parsed.text_other += other
                    elif block.get("type") != "thinking":
                        parsed.text_only = False
            elif kind == "boundary":
                if record.get("subtype") != "compact_boundary":
                    continue
                meta = record.get("compactMetadata") or {}
                timestamp = parse_timestamp(record["timestamp"])
                key = (timestamp, meta.get("preTokens") or 0)
                if key in seen_boundaries:
                    continue
                seen_boundaries.add(key)
                transcript.boundaries.append(
                    _Boundary(
                        position=len(transcript.messages),
                        timestamp=timestamp,
                        trigger=meta.get("trigger") or "unknown",
                        pre_tokens=meta.get("preTokens") or 0,
                        duration_seconds=(meta.get("durationMs") or 0) / 1_000,
                    )
                )
            elif record.get("isCompactSummary") and transcript.boundaries:
                message = record.get("message") or {}
                content = message.get("content")
                text = content if isinstance(content, str) else json.dumps(content)
                boundary = transcript.boundaries[-1]
                boundary.summary_cjk, boundary.summary_other = _char_classes(text)
    return transcript


def _fit_token_estimator(
    transcripts: list[_Transcript],
) -> tuple[float, float, int]:
    """Tokens per CJK char and per other char, fitted on plain answers.

    Plain answers are end_turn messages made only of text (plus thinking,
    whose tokens are subtracted), so output_tokens is a known function of the
    visible text.
    """
    points: list[list[float]] = []
    values: list[float] = []
    for transcript in transcripts:
        for message in transcript.messages:
            chars = message.text_cjk + message.text_other
            if (
                message.stop_reason == "end_turn"
                and message.text_only
                and chars >= CALIBRATION_MIN_CHARS
            ):
                points.append([float(message.text_cjk), float(message.text_other)])
                values.append(float(message.output_tokens - message.thinking_tokens))
    per_cjk, per_other = _fit_no_intercept(points, values)
    return per_cjk, per_other, len(points)


def _uncached_multiplier(messages: list[_Message], profile: Profile) -> float:
    """Token-weighted price of uncached tokens relative to the input price."""
    price = profile.prices
    cost = sum(
        m.input_tokens * price["input"]
        + m.written_5m * price["cache_write_5m"]
        + m.written_1h * price["cache_write_1h"]
        for m in messages
    )
    tokens = sum(m.input_tokens + m.written_5m + m.written_1h for m in messages)
    return cost / (tokens * price["input"]) if tokens else 1.0


def _active_seconds(
    messages: list[_Message],
    boundaries: list[_Boundary],
    idle_gap: float,
) -> float:
    """Agent working time: request gaps up to idle_gap, minus compaction time."""
    total = 0.0
    for previous, current in zip(messages, messages[1:]):
        gap = current.timestamp - previous.timestamp
        for boundary in boundaries:
            if previous.timestamp <= boundary.timestamp <= current.timestamp:
                gap -= boundary.duration_seconds
        if 0 < gap <= idle_gap:
            total += gap
    return total


def collect(
    root: Path,
    profile: Profile,
) -> Collected:
    """Sessions, compactions (as calibration compactions), measured profile, stats."""
    prefixes = profile.model_prefixes
    seen_messages: set[str] = set()
    seen_boundaries: set[tuple[float, int]] = set()
    transcripts: list[_Transcript] = []
    excluded: Counter[str] = Counter()
    for path in sorted(root.rglob("*.jsonl")):
        transcript = _read_transcript(path, seen_messages, seen_boundaries, prefixes)
        if transcript.messages:
            transcripts.append(transcript)
        else:
            excluded["no-matching-model-requests"] += 1

    per_cjk, per_other, estimator_points = _fit_token_estimator(transcripts)
    sessions: list[Session] = []
    compactions: list[CompactionSample] = []
    post_contexts: list[int] = []
    post_uncached: list[int] = []
    skipped: Counter[str] = Counter()
    found: Counter[str] = Counter()
    for transcript in transcripts:
        messages = transcript.messages
        boundaries = transcript.boundaries
        sessions.append(
            Session(
                requests=chain_requests(
                    [Request(m.context, m.cache_read, m.output_tokens) for m in messages],
                    [b.position for b in boundaries],
                ),
                task_seconds=_active_seconds(
                    messages, boundaries, profile.harness_cfg["idle_gap_seconds"]
                ),
                segment="subagent" if transcript.subagent else "main",
                uncached_multiplier=_uncached_multiplier(messages, profile),
            )
        )
        where = "subagent" if transcript.subagent else "main"
        for boundary in boundaries:
            before = messages[boundary.position - 1] if boundary.position else None
            after = (
                messages[boundary.position]
                if boundary.position < len(messages)
                else None
            )
            found[f"{boundary.trigger}-{where}"] += 1
            if after is not None:
                post_contexts.append(after.context)
                post_uncached.append(
                    after.input_tokens + after.written_5m + after.written_1h
                )
            if before is None:
                skipped["no-request-before"] += 1
            elif boundary.duration_seconds <= 0 or boundary.pre_tokens <= 0:
                skipped["no-duration-or-size"] += 1
            elif boundary.summary_cjk is None:
                skipped["no-summary"] += 1
            else:
                tail = max(0, boundary.pre_tokens - before.context)
                compactions.append(
                    CompactionSample(
                        name=f"compaction-{len(compactions) + 1:03d}",
                        input_tokens=boundary.pre_tokens,
                        cached_tokens=boundary.pre_tokens - tail,
                        output_tokens=round(
                            per_cjk * boundary.summary_cjk
                            + per_other * boundary.summary_other
                        ),
                        seconds=boundary.duration_seconds,
                        source=f"transcript-{boundary.trigger}",
                    )
                )
    if not sessions or not compactions:
        raise ValueError("No matching sessions or compactions were found")
    stats = {
        "included_sessions_main": sum(s.segment == "main" for s in sessions),
        "included_sessions_subagent": sum(s.segment == "subagent" for s in sessions),
        "max_input_tokens": max(
            m.context for t in transcripts for m in t.messages
        ),
        "compactions_found": dict(found),
        "compactions_used": len(compactions),
        "compactions_excluded": dict(skipped),
        "summary_tokens_per_cjk_char": per_cjk,
        "summary_tokens_per_other_char": per_other,
        "summary_estimator_messages": estimator_points,
        "observed_compaction_input_median": round(
            statistics.median(t.input_tokens for t in compactions)
        ),
        "observed_auto_compaction_median": round(
            statistics.median(
                t.input_tokens for t in compactions if t.source == "transcript-auto"
            )
        ),
        "mean_uncached_multiplier": statistics.fmean(
            s.uncached_multiplier for s in sessions
        ),
    }
    measured = profile.with_measured(
        round(statistics.median(post_contexts)),
        round(statistics.median(post_uncached)),
    )
    messages = [m for t in transcripts for m in t.messages]
    billing_mix = {
        "uncached_input": sum(m.input_tokens for m in messages),
        "cache_write_5m": sum(m.written_5m for m in messages),
        "cache_write_1h": sum(m.written_1h for m in messages),
        "cache_read": sum(m.cache_read for m in messages),
        "output": sum(m.output_tokens for m in messages),
    }
    return Collected(sessions, dict(excluded), compactions, measured, stats, billing_mix)
