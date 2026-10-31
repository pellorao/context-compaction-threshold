from __future__ import annotations

import itertools
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from harness import collect  # noqa: E402
from model_profile import load_profile  # noqa: E402


COUNTER = itertools.count(1)


def uid(number: int) -> str:
    return f"{number:036x}"


def entry(record: dict, parent: str | None = None, uuid: str | None = None) -> dict:
    """Order the fields as Claude Code writes them: parentUuid first, then uuid and timestamp."""
    timestamp = record.pop("timestamp")
    return {"parentUuid": parent, **record, "uuid": uuid or uid(next(COUNTER)), "timestamp": timestamp}


def at(second: int) -> str:
    return f"2026-10-01T00:00:{second:02d}.000Z"


def assistant(message_id, model, usage, second, *, output=10, stop=None, parent=None):
    return entry({
        "type": "assistant",
        "timestamp": at(second),
        "message": {
            "id": message_id,
            "model": model,
            "stop_reason": stop,
            "content": [{"type": "text", "text": "x" * 300}],
            "usage": {
                "input_tokens": usage[0],
                "cache_creation_input_tokens": usage[1] + usage[2],
                "cache_creation": {
                    "ephemeral_5m_input_tokens": usage[1],
                    "ephemeral_1h_input_tokens": usage[2],
                },
                "cache_read_input_tokens": usage[3],
                "output_tokens": output,
            },
        },
    }, parent)


def write(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Claude Code writes compact JSON; the loader relies on it to skip lines fast.
    lines = (json.dumps(r, separators=(",", ":")) for r in records)
    path.write_text("\n".join(lines) + "\n")


class ClaudeSourceTest(unittest.TestCase):
    def test_loads_opus_requests_compactions_and_chains_segments(self) -> None:
        opus = "claude-opus-5-5"
        boundary = {
            "type": "system",
            "subtype": "compact_boundary",
            "timestamp": "2026-10-01T00:00:30.000Z",
            "compactMetadata": {
                "trigger": "auto",
                "preTokens": 100_000,
                "durationMs": 40_000,
            },
        }
        summary = entry({
            "type": "user",
            "isCompactSummary": True,
            "timestamp": at(31),
            "message": {"content": "s" * 3_000},
        }, uuid=uid(900))
        user = lambda number, second: entry(
            {"type": "user", "timestamp": at(second), "message": {"content": "q"}},
            uuid=uid(number),
        )
        # A hook attachment written long after the response it precedes (t=50):
        # the request is timed from the user entry before it, not from it.
        attachment = entry(
            {"type": "attachment", "attachment": {"type": "hook"}, "timestamp": at(50)},
            parent=uid(902), uuid=uid(903),
        )
        main = [
            user(901, 0),
            assistant("m1", opus, (10, 0, 5_000, 0), 2, parent=uid(901)),
            user(902, 3),
            attachment,
            # One response split over two lines: the last line has the output.
            assistant("m2", opus, (10, 0, 1_000, 5_000), 5, output=3, parent=uid(903)),
            assistant("m2", opus, (10, 0, 1_000, 5_000), 5, output=300, stop="end_turn"),
            assistant("h1", "claude-haiku-5-5", (1, 0, 9_000, 0), 6),
            boundary,
            summary,
            assistant("m3", opus, (10, 0, 20_000, 3_000), 40, parent=uid(900)),
            user(904, 42),
            assistant("m4", opus, (10, 0, 500, 23_000), 45, parent=uid(904)),
        ]
        sub = [assistant("s1", opus, (10, 2_000, 0, 0), 0)]
        # Plain answers calibrate tokens per CJK and per other character:
        # 1 token per CJK char and 0.5 per other char.
        for index, (cjk, other) in enumerate([(300, 100), (100, 600), (50, 900)]):
            record = assistant(
                f"t{index}", opus, (10, 0, 0, 2_000), 10 + index,
                output=cjk + other // 2, stop="end_turn",
            )
            record["message"]["content"] = [
                {"type": "text", "text": "字" * cjk + "x" * other}
            ]
            sub.append(record)
        haiku_only = [assistant("h2", "claude-haiku-5-5", (1, 0, 10, 0), 0)]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write(root / "p" / "a.jsonl", main)
            # A resumed copy repeats messages and the boundary.
            write(root / "p" / "b.jsonl", main[:3] + [boundary])
            write(root / "p" / "a" / "subagents" / "agent-1.jsonl", sub)
            write(root / "p" / "c.jsonl", haiku_only)
            profile = load_profile("claude-opus-5-5")
            collected = collect(profile, root)
        sessions, excluded = collected.sessions, collected.excluded
        compactions, measured, stats = collected.compactions, collected.profile, collected.stats

        self.assertEqual(len(sessions), 2)
        self.assertAlmostEqual(stats["summary_tokens_per_cjk_char"], 1.0, places=1)
        self.assertAlmostEqual(stats["summary_tokens_per_other_char"], 0.5, places=1)
        self.assertEqual(excluded, {"no-matching-model-requests": 2})
        self.assertEqual(stats["included_sessions_main"], 1)
        self.assertEqual(stats["included_sessions_subagent"], 1)
        by_segment = {session.segment: session for session in sessions}
        main_session, sub_session = by_segment["main"], by_segment["subagent"]
        # Opus only, one usage per message id.
        self.assertEqual(len(main_session.requests), 4)
        self.assertEqual(main_session.requests[1].output_tokens, 300)
        self.assertEqual(main_session.requests[1].input_tokens, 5_000 + 1_000 + 10)
        self.assertEqual(main_session.requests[1].cached_tokens, 5_000)
        # The segment after the compaction continues from the context before it
        # by one typical increment instead of resetting to about 23k.
        contexts = [r.input_tokens for r in main_session.requests]
        self.assertGreater(contexts[2], contexts[1])
        self.assertTrue(all(b > a for a, b in zip(contexts, contexts[1:])))
        # Main thread writes at the 1-hour price (2x input), subagents at 5 minutes.
        self.assertAlmostEqual(main_session.uncached_multiplier, 2.0, places=2)
        self.assertAlmostEqual(sub_session.uncached_multiplier, 1.25, places=2)
        # A request lasts from the nearest user or assistant entry before it to
        # its last streamed line; attachments are skipped.
        self.assertEqual([r.seconds for r in main_session.requests], [2, 2, 9, 3])
        # One calibration compaction, duplicates collapsed.
        self.assertEqual(len(compactions), 1)
        self.assertEqual(stats["compactions_used"], 1)
        self.assertEqual(compactions[0].input_tokens, 100_000)
        self.assertEqual(compactions[0].seconds, 40.0)
        self.assertEqual(compactions[0].source, "transcript-auto")
        self.assertEqual(measured.post_context, 20_000 + 3_000 + 10)
        self.assertEqual(measured.post_cold_uncached, 20_010)
        serialized = json.dumps([stats, compactions[0].name, compactions[0].source])
        self.assertNotIn("subagents", serialized)
        self.assertNotIn(directory, serialized)


if __name__ == "__main__":
    unittest.main()
