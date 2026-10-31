from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from analysis import _replay_session, fit_model, load_compactions  # noqa: E402
from harness import collect  # noqa: E402
from model_profile import load_profile  # noqa: E402


def _at(seconds: float) -> str:
    start = datetime(2026, 10, 1, tzinfo=timezone.utc)
    return (start + timedelta(seconds=seconds)).isoformat()


def _event(kind: str, subtype: str | None, seconds: float, **payload: object) -> dict:
    return {
        "type": kind,
        "timestamp": _at(seconds),
        "payload": {"type": subtype, **payload},
    }


def _request(
    index: int, input_tokens: int, cached: int, output: int, seconds: float = 0.0
) -> dict:
    return {
        "type": "token_usage_record",
        "timestamp": _at(seconds),
        "payload": {
            "response_id": f"r{index}",
            "usage": {
                "input_tokens": input_tokens,
                "cached_input_tokens": cached,
                "output_tokens": output,
            },
        },
    }


class CodexCompactionTest(unittest.TestCase):
    def test_compaction_at_new_turn_does_not_include_user_wait(self) -> None:
        lines = [
            {"type": "session_meta", "payload": {"model_provider": "deepseek", "cwd": "/work"}},
            _event("response_item", "function_call_output", 0),
            _request(1, 100_000, 90_000, 500, 4),
            _event("event_msg", "token_count", 4),
            _event("event_msg", "task_started", 100_000),
            _request(2, 150_000, 5000, 2000, 100_020),
            _event("event_msg", "token_count", 100_020),
            _event("compacted", None, 100_020.2, compaction_response_id="c1"),
            _request(3, 20_000, 5000, 400, 100_025),
        ]
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "session.jsonl").write_text(
                "\n".join(json.dumps(r) for r in lines) + "\n"
            )
            collected = collect(load_profile("deepseek-flash"), Path(directory))
        self.assertAlmostEqual(collected.compactions[0].seconds, 20.2)
        self.assertEqual(sum(len(s.requests) for s in collected.sessions), 2)

    def test_recent_sessions_filter_before_dedup_and_measure_post_compaction(self) -> None:
        profile = load_profile("gpt-6.1-sol")
        day = 86400
        cutoff, end = 14 * day, 28 * day

        def session(start: int | None, compact: bool = True) -> list[dict]:
            meta = {"id": "work", "cwd": "/work"}
            if start is not None:
                meta["timestamp"] = _at(start)
            lines = [
                {"type": "session_meta", "payload": meta},
                {"type": "turn_context", "payload": {"model": profile.model}},
                _event("response_item", "function_call_output", end - 100),
                _request(1 if compact else 1000, 100_000, 90_000, 500, end - 98),
                _event("event_msg", "token_count", end - 98),
            ]
            if compact:
                lines.extend([
                    _request(2, 150_000, 20_000, 2000, end - 78),
                    _event("event_msg", "token_count", end - 78),
                    _event("compacted", None, end - 77.8, compaction_response_id="c1"),
                    _request(3, 35_000, 10_000, 400, end - 72),
                    _event("response_item", "function_call_output", end - 70),
                    _request(4, 40_000, 35_000, 300, end - 68),
                ])
            return lines

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, started, compact in (
                ("a-old", cutoff - 1, True),
                ("b-boundary", cutoff, True),
                ("c-no-compaction", end, False),
                ("d-future", end + 1, True),
                ("e-unknown", None, True),
            ):
                (root / f"{name}.jsonl").write_text(
                    "\n".join(json.dumps(r) for r in session(started, compact)) + "\n"
                )
            collected = collect(
                profile, root, snapshot_at=datetime.fromisoformat(_at(end))
            )
        self.assertEqual(len(collected.sessions), 2)
        self.assertEqual(sum(len(s.requests) for s in collected.sessions), 4)
        self.assertEqual(len(collected.compactions), 1)
        self.assertEqual(collected.compactions[0].input_tokens, 150_000)
        self.assertEqual(collected.profile.post_context, 35_000)
        self.assertEqual(collected.profile.post_cold_uncached, 25_000)
        self.assertEqual(collected.stats["requests_without_duration"], 0)
        self.assertEqual(collected.stats["session_selection"]["max_age_days"], 14)
        self.assertEqual(collected.excluded, {
            "session-start-outside-window": 2, "session-start-unknown": 1,
        })
        self.assertEqual(sum(collected.billing_mix.values()), 276_700)

    def test_real_compactions_are_chained_not_replayed_as_negative_context(self) -> None:
        profile = load_profile("deepseek-flash")
        usage = [
            (20_000, 10_000, 500),
            (60_000, 55_000, 600),
            (100_000, 95_000, 700),
            # The compaction request: logged just before the compacted record.
            (98_000, 4_000, 3_000),
            (24_000, 12_000, 400),
            (40_000, 24_000, 500),
        ]
        lines = [{"type": "session_meta", "payload": {"id": "t", "model_provider": "deepseek", "cwd": "/work"}}]
        # Request k starts at a tool output at 100k and ends 4 s later, except
        # the request after the compaction, which starts when it ends.
        for index, item in enumerate(usage):
            start = 100.0 * index
            if index != 4:
                lines.append(_event("response_item", "function_call_output", start))
            lines.append(_request(index, *item, seconds=start + 4))
            lines.append(_event("event_msg", "token_count", start + 4))
            if index == 3:
                lines.append(_event("compacted", None, 304.2, compaction_response_id="c1"))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rollout.jsonl"
            path.write_text("\n".join(json.dumps(line) for line in lines) + "\n")
            collected = collect(profile, Path(directory))
        session = collected.sessions[0]
        # The compaction request is gone and no context ever shrinks.
        self.assertEqual(len(session.requests), 5)
        # A request lasts from its input (tool output) to its usage record; the
        # one after the compaction starts when the compaction ends.
        self.assertEqual([round(r.seconds, 1) for r in session.requests], [4, 4, 4, 99.8, 4])
        # The compaction became a sample: the compaction request's own usage,
        # timed from the last token_count more than 1 s before the compacted
        # record (the end of request 2 at t=204; the request's own token_count
        # at t=304 is too close to count).
        (sample,) = collected.compactions
        self.assertEqual(
            (sample.name, sample.input_tokens, sample.cached_tokens, sample.output_tokens, sample.source),
            ("log-001", 98_000, 4_000, 3_000, "log-auto"),
        )
        self.assertAlmostEqual(sample.seconds, 100.2)
        inputs = [r.input_tokens for r in session.requests]
        self.assertEqual(inputs, sorted(inputs))
        # Billing mix counts the logged requests without the compaction request.
        self.assertEqual(
            sum(collected.billing_mix.values()),
            sum(i + o for k, (i, c, o) in enumerate(usage) if k != 3),
        )
        self.assertEqual(collected.stats["max_input_tokens"], 100_000)

        # Without compaction the replay costs exactly the chained requests.
        model = fit_model(load_compactions(ROOT / profile.compactions_path), profile)
        replay = _replay_session(
            session, 10**12, model, profile, cached_prefix=model.central_cached_prefix
        )
        direct = sum(
            (r.input_tokens - r.cached_tokens)
            + profile.alpha * r.cached_tokens
            + profile.output_over_miss * r.output_tokens
            for r in session.requests
        )
        self.assertAlmostEqual(replay["cost_units"], direct)
        for threshold in (64_000, 90_000, 200_000):
            result = _replay_session(
                session, threshold, model, profile,
                cached_prefix=model.central_cached_prefix,
            )
            self.assertGreater(result["cost_units"], 0)

    def test_provider_match_does_not_pull_in_other_models(self) -> None:
        profile = load_profile("deepseek-flash")
        with tempfile.TemporaryDirectory() as directory:
            for name, model in (("a", "deepseek-flash"), ("b", "deepseek-v4-pro")):
                lines = [
                    {"type": "session_meta", "payload": {"id": name, "model_provider": "deepseek", "cwd": "/work"}},
                    {"type": "turn_context", "payload": {"model": model}},
                    _event("response_item", "function_call_output", 0),
                    _request(ord(name), 20_000, 10_000, 500, 1),
                    _event("response_item", "function_call_output", 2),
                    _request(ord(name) + 100, 30_000, 20_000, 500, 3),
                ]
                (Path(directory) / f"{name}.jsonl").write_text(
                    "\n".join(json.dumps(line) for line in lines) + "\n"
                )
            collected = collect(profile, Path(directory))
        self.assertEqual(len(collected.sessions), 1)
        self.assertEqual(collected.excluded, {"other-model": 1})


if __name__ == "__main__":
    unittest.main()
