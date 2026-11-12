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
    COUNT_DECIMALS,
    LANDING_NAME,
    fill_template,
    load_pages,
    render_landing,
    render_model,
    window_for,
)


def _curve(rows: int) -> list[dict]:
    out = []
    for i in range(rows):
        row = {
            "threshold": 68_000 + 2_000 * i,
            "cost_usd_off_peak": 100.0 + abs(i - 5),
            "compactions": 10.0,
            "compaction_seconds": 100.0,
            "compaction_prefill_seconds": 20.0,
            "compaction_output_seconds": 80.0,
            "request_seconds": 1900.0,
            "request_seconds_slope_lo": 1850.0,
            "request_seconds_slope_hi": 1950.0,
            "time_share": 0.05,
            "feasible_time": True,
        }
        row["cost_per_million_tokens"] = row["cost_usd_off_peak"] / 100
        out.append(row)
    return out


def _result(trigger: bool) -> dict:
    snapshot = {
        "requests": 100, "request_seconds": 3600.0, "included_sessions": 3,
        "included_active_tail": False,
        "session_selection": {
            "max_age_days": 14,
            "started_at_or_after": "2026-10-18T00:00:00+00:00",
            "started_at_or_before": "2026-11-01T00:00:00+00:00",
        },
    }
    snapshot["billed_tokens"] = 1_000_000
    snapshot["billing_mix"] = {
        "uncached_input": 0, "cache_write_5m": 30_000,
        "cache_write_1h": 10_000, "cache_read": 950_000, "output": 10_000,
    }
    if trigger:
        snapshot["observed_auto_compaction_median"] = 267_000
        snapshot["included_sessions_main"] = 1
        snapshot["included_sessions_subagent"] = 2
    curves = {k: _curve(40) for k in ("central", "cost_low", "cost_high")}
    return {
        "snapshot": snapshot,
        "fitted_model": {
            "time_r2_two_factor": 0.9, "time_r2_output_only": 0.8,
            "time_r2_input_only": 0.1, "output_speed_tokens_per_second": 150.0,
            "bootstrap_replicates": 100, "bootstrap_block_requests": 8,
            "request_seconds_per_context_token": 3.5e-6,
            "request_seconds_per_context_token_low": 1e-6,
            "request_seconds_per_context_token_high": 6e-6,
        },
        "measurements": [{"source": "log-auto"}] * 6 + [{"source": "native"}] * 3,
        "curves": curves,
    }


class RenderTest(unittest.TestCase):
    def setUp(self) -> None:
        self.pages = load_pages()
        self.labels = {n: load_profile(n).label for n in profile_names()}

    def model_page(self, name: str, trigger: bool) -> str:
        return render_model(
            _result(trigger), load_profile(name), self.pages, self.labels
        )

    def test_model_page_has_both_languages_and_no_leftover_placeholders(self) -> None:
        html = self.model_page("claude-opus-5-5", True)
        for lang in ("en", "zh"):
            self.assertIn(f'<span data-l="{lang}">', html)
        body = html.split("<body", 1)[1].split("<script>", 1)[0]
        self.assertIsNone(re.search(r"\{[a-z_0-9]+\}|\[\[|\{\?", body))
        self.assertIn(GITHUB_URL, html)
        self.assertEqual(GITHUB_URL, "https://github.com/pellorao/context-compaction-threshold")

    def test_subscription_pages_use_own_recent_log_fit_and_no_deepseek_claims(self) -> None:
        for name in ("gpt-6.1-sol", "gpt-6.1-terra", "gpt-6-luna"):
            html = self.model_page(name, False)
            main, details = html.split("<details", 1)
            self.assertNotIn("872K", main)
            self.assertIn("872K", details)
            self.assertIn("828K", html)
            self.assertIn("2026-10-18T00:00:00Z", details)
            self.assertIn("14 days", details)
            self.assertIn("Fitting the real requests", details)
            self.assertNotIn("DeepSeek", html)
            self.assertNotIn("trimmed", details)
            body = html.split("<body", 1)[1].split("<script>", 1)[0]
            self.assertIsNone(re.search(r"\{[a-z_0-9]+\}|\[\[|\{\?", body))

    def test_time_share_is_described_as_model_request_time(self) -> None:
        for name, trigger in (("claude-opus-5-5", True), ("deepseek-flash", False)):
            html = self.model_page(name, trigger)
            self.assertIn("share of model request time spent compacting", html)
            for old in ("agent time", "working time", "workSeconds", "clock on your wall", "requestSeconds"):
                self.assertNotIn(old, html)

    def test_chart_is_relative_to_the_largest_trigger_with_two_lines(self) -> None:
        html = self.model_page("claude-opus-5-5", True)
        self.assertIn("Cost vs 966K", html)  # tooltip and pick card
        self.assertIn("relCost", html)
        for gone in ("legend-work", "work-line", "work-band", "relWork", "plum"):
            self.assertNotIn(gone, html)
        self.assertIn("Request time grows with context", html.split("<details", 1)[1])
        self.assertIn("0.35 s", html)  # slope per 100K tokens from the fixture

    def test_two_stacked_charts_and_total_time_line_on_every_page(self) -> None:
        for name, trigger, top in (("claude-opus-5-5", True, "966K"), ("claude-sonnet-5-5", True, "966K"), ("deepseek-flash", False, "900K")):
            html = self.model_page(name, trigger)
            self.assertIn('id="chart-cost"', html)
            self.assertIn('id="chart-time"', html)
            self.assertIn('"legend_total"', html)
            self.assertIn("total-line", html)
            self.assertIn(f"Total model time vs {top}", html)
        self.assertNotIn("picks_extra", html)

    def test_no_total_time_sentence_remains(self) -> None:
        for name in ("claude-opus-5-5", "deepseek-flash"):
            html = self.model_page(name, name != "deepseek-flash")
            for gone in ("total-time", "renderTotal", "total_time", 'class="hl"', ".hl "):
                self.assertNotIn(gone, html)

    def test_time_chart_has_one_shared_axis_with_fixed_top(self) -> None:
        html = self.model_page("claude-opus-5-5", True)
        self.assertIn('"timeAxisMax": 0.2', html)
        self.assertIn("Time (%)", html)
        self.assertNotIn("y_time_right", html)
        self.assertNotIn("(right axis)", html)

    def test_left_axis_fits_the_cost_band(self) -> None:
        html = self.model_page("claude-opus-5-5", True)
        self.assertIn("axisFit", html)
        self.assertNotIn("axis5", html)
        self.assertIn("Cost change (vs. 966K trigger)", html)

    def test_top_bar_is_not_sticky_or_fixed(self) -> None:
        html = self.model_page("claude-opus-5-5", True)
        self.assertNotIn("position:fixed", html.replace(" ", ""))
        self.assertNotIn("position:sticky", html.replace(" ", ""))

    def test_claude_page_shows_window_and_per_million_mix(self) -> None:
        html = self.model_page("claude-opus-5-5", True)
        self.assertIn("autoCompactWindow", html)
        self.assertIn("95.0% cache reads", html)
        self.assertIn("Cost per 1M tokens", html)

    def test_picks_are_two_groups_and_compactions_are_per_million(self) -> None:
        html = self.model_page("claude-opus-5-5", True)
        self.assertIn('"picks_g1": "Cheapest overall"', html)
        self.assertIn('"pick_limit": "Up to %limit%"', html)
        self.assertIn('"tip_n": "Compactions per 1M tokens"', html)
        self.assertIn('"billedM": 1.0', html)
        self.assertNotIn('id="readout"', html)

    def test_count_decimals_keep_two_significant_digits_on_every_grid(self) -> None:
        smallest = []
        for name in profile_names():
            profile = load_profile(name)
            result = json.loads((ROOT / profile.data_dir / "result.json").read_text())
            per_million = result["snapshot"]["billed_tokens"] / 1e6
            smallest.append(
                min(row["compactions"] for row in result["curves"]["central"]) / per_million
            )
        self.assertGreaterEqual(round(min(smallest), COUNT_DECIMALS) * 10**COUNT_DECIMALS, 10)

    def test_triggers_are_whole_k_and_never_written_in_tokens(self) -> None:
        html = self.model_page("deepseek-flash", False)
        self.assertNotIn("Math.round(n).toLocaleString", html)
        self.assertNotIn("Trigger at", html)

    def test_window_is_rounded_to_whole_thousands(self) -> None:
        self.assertEqual(window_for(68_000, 33_000), 101_000)
        self.assertEqual(window_for(66_200, 32_100), 98_000)
        self.assertEqual(window_for(66_500, 32_000), 99_000)
        html = self.model_page("claude-opus-5-5", True)
        self.assertIn("Math.round((t+D.buffer)/1000)*1000", html)

    def test_evidence_text_is_inside_the_collapsed_details(self) -> None:
        html = self.model_page("claude-opus-5-5", True)
        main, details = html.split("<details", 1)
        self.assertNotIn("three sources", main)
        self.assertNotIn("Why the buffer is", main)
        self.assertIn("three sources", details)
        self.assertIn("Why the buffer is 33K", details)

    def test_pages_show_no_dollar_amounts(self) -> None:
        for name, trigger in (
            ("claude-opus-5-5", True), ("deepseek-flash", False),
            *((name, False) for name in ("gpt-6.1-sol", "gpt-6.1-terra", "gpt-6-luna")),
        ):
            html = self.model_page(name, trigger)
            self.assertNotIn("per_m", html)
            self.assertNotIn("usd(", html)
            # page text: the body and the translation table, not the page script
            visible = html.split("<body", 1)[1].split("const T=", 1)
            visible = visible[0] + visible[1].split("\n", 1)[0]
            for word in ("$", "USD", "dollar", "price", "美元", "价格"):
                self.assertNotIn(word, visible, word)

    def test_conditional_lines_need_text(self) -> None:
        per_lang = {"en": {"a": "yes", "b": ""}, "zh": {"a": "是", "b": ""}}
        out = fill_template("{?a}[[a]]\n{?b}[[b]]\nplain", per_lang)
        self.assertIn("yes", out)
        self.assertNotIn("<span data-l=\"en\"></span>", out)
        self.assertIn("plain", out)

    def test_landing_lists_every_model_and_links_pages(self) -> None:
        results = {n: _result(load_profile(n).trigger is not None) for n in profile_names()}
        profiles = {n: load_profile(n) for n in results}
        html = render_landing(results, profiles, self.pages, self.labels)
        for name in results:
            self.assertIn(f'href="{name}.html"', html)
        self.assertEqual(LANDING_NAME, "index.html")


class RenderOnlyTest(unittest.TestCase):
    def test_write_site_writes_landing_and_model_pages(self) -> None:
        from generate import write_site

        results = {n: _result(load_profile(n).trigger is not None) for n in profile_names()}
        profiles = {n: load_profile(n) for n in results}
        with tempfile.TemporaryDirectory() as directory:
            site = Path(directory)
            write_site(site, results, profiles)
            names = {p.name for p in site.iterdir()}
            self.assertEqual(names, {f"{n}.html" for n in results} | {"index.html"})


if __name__ == "__main__":
    unittest.main()
