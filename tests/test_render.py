from __future__ import annotations

import copy
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from model_profile import load_profile, profile_names  # noqa: E402
from render import (  # noqa: E402
    GITHUB_URL,
    LANDING_NAME,
    fill_template,
    load_pages,
    render_landing,
    render_model,
)


def _curve(rows: int, per_million: bool) -> list[dict]:
    out = []
    for i in range(rows):
        row = {
            "threshold": 67_000 + 2_000 * i,
            "cost_usd_off_peak": 100.0 + abs(i - 5),
            "compactions": 10.0,
            "compaction_seconds": 100.0,
            "compaction_prefill_seconds": 20.0,
            "compaction_output_seconds": 80.0,
            "time_share": 0.05,
            "feasible_time": True,
        }
        if per_million:
            row["cost_per_million_tokens"] = row["cost_usd_off_peak"] / 100
        out.append(row)
    return out


def _result(per_million: bool, trigger: bool) -> dict:
    snapshot = {
        "requests": 100, "work_seconds": 3600.0, "included_sessions": 3,
        "included_active_tail": False,
    }
    if per_million:
        snapshot["billed_tokens"] = 1_000_000
        snapshot["billing_mix"] = {
            "uncached_input": 0, "cache_write_5m": 30_000,
            "cache_write_1h": 10_000, "cache_read": 950_000, "output": 10_000,
        }
    if trigger:
        snapshot["observed_auto_compaction_median"] = 267_000
        snapshot["included_sessions_main"] = 1
        snapshot["included_sessions_subagent"] = 2
    curves = {k: _curve(40, per_million) for k in ("central", "cost_low", "cost_high")}
    return {
        "snapshot": snapshot,
        "fitted_model": {
            "time_r2_two_factor": 0.9, "time_r2_output_only": 0.8,
            "time_r2_input_only": 0.1, "output_speed_tokens_per_second": 150.0,
            "bootstrap_replicates": 100, "bootstrap_block_requests": 8,
        },
        "measurements": [{}] * 9,
        "curves": curves,
    }


class RenderTest(unittest.TestCase):
    def setUp(self) -> None:
        self.pages = load_pages()
        self.labels = {n: load_profile(n).label for n in profile_names()}

    def model_page(self, name: str, per_million: bool, trigger: bool) -> str:
        return render_model(
            _result(per_million, trigger), load_profile(name), self.pages, self.labels
        )

    def test_model_page_has_both_languages_and_no_leftover_placeholders(self) -> None:
        html = self.model_page("claude-opus-5-5", True, True)
        for lang in ("en", "zh"):
            self.assertIn(f'<span data-l="{lang}">', html)
        body = html.split("<body", 1)[1].split("<script>", 1)[0]
        self.assertIsNone(re.search(r"\{[a-z_0-9]+\}|\[\[|\{\?", body))
        self.assertIn(GITHUB_URL, html)
        self.assertEqual(GITHUB_URL, "https://github.com/pellorao/context-compaction-threshold")

    def test_top_bar_is_not_sticky_or_fixed(self) -> None:
        html = self.model_page("claude-opus-5-5", True, True)
        self.assertNotIn("position:fixed", html.replace(" ", ""))
        self.assertNotIn("position:sticky", html.replace(" ", ""))

    def test_claude_page_shows_window_and_per_million_mix(self) -> None:
        html = self.model_page("claude-opus-5-5", True, True)
        self.assertIn("autoCompactWindow", html)
        self.assertIn("95.0% cache reads", html)
        self.assertIn("Cost per 1M tokens", html)

    def test_total_dollar_result_keeps_total_cost_wording(self) -> None:
        html = self.model_page("deepseek-flash", False, False)
        self.assertNotIn("Cost per 1M tokens", html)
        self.assertNotIn("autoCompactWindow", html)  # no window text outside Claude Code
        self.assertIn("Estimated cost (USD)", html)

    def test_conditional_lines_need_text(self) -> None:
        per_lang = {"en": {"a": "yes", "b": ""}, "zh": {"a": "是", "b": ""}}
        out = fill_template("{?a}[[a]]\n{?b}[[b]]\nplain", per_lang)
        self.assertIn("yes", out)
        self.assertNotIn("<span data-l=\"en\"></span>", out)
        self.assertIn("plain", out)

    def test_landing_lists_every_model_and_links_pages(self) -> None:
        results = {
            "deepseek-flash": _result(False, False),
            "claude-opus-5-5": _result(True, True),
            "claude-sonnet-5-5": _result(True, True),
        }
        profiles = {n: load_profile(n) for n in results}
        html = render_landing(results, profiles, self.pages, self.labels)
        for name in results:
            self.assertIn(f'href="{name}.html"', html)
        self.assertEqual(LANDING_NAME, "threshold-chart.html")


class RenderOnlyTest(unittest.TestCase):
    def test_render_only_writes_landing_and_index(self) -> None:
        from generate import write_site

        results = {n: _result(n != "deepseek-flash", n != "deepseek-flash") for n in profile_names()}
        profiles = {n: load_profile(n) for n in results}
        with tempfile.TemporaryDirectory() as directory:
            site = Path(directory)
            write_site(site, results, profiles)
            names = {p.name for p in site.iterdir()}
            self.assertEqual(
                names,
                {f"{n}.html" for n in results} | {"threshold-chart.html", "index.html"},
            )
            self.assertEqual(
                (site / "index.html").read_text(),
                (site / "threshold-chart.html").read_text(),
            )


if __name__ == "__main__":
    unittest.main()
