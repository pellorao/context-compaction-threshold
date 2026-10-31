English | [简体中文](README.zh-CN.md)

# Context Compaction Threshold

An empirical calculator for the trade-off between token cost and
context-compaction time. It replays real agent sessions, fits a cost and
latency model from measured compactions, expands the observed workload with a
block bootstrap, and publishes a static site: a landing page where you pick a
model, and one chart page per model (DeepSeek Flash on Codex, Claude Opus 5.5
and Claude Sonnet 5.5 on Claude Code). Pages are in English and Simplified
Chinese.

[View the live report](https://deepseek-compaction-threshold.pages.dev/)

The chart has no universal winner. The useful threshold depends on how much
working context you need and how much compaction cost and delay you accept.
For Claude Code the page also tells you which `autoCompactWindow` value to set.

The fixed rules (threshold step, axis limits, prices and their sources, what
counts as a session or request, how compactions are found, bootstrap
parameters) and the per-model data statistics are in
[docs/methodology.md](docs/methodology.md).

## Quick start

No third-party Python dependencies.

```bash
python3 src/generate.py --profile claude-opus-5-5 --workers 30   # analyze, then rebuild the site
python3 src/generate.py --render-only                           # rebuild the site from existing results
python3 -m unittest discover -s tests -p 'test_*.py'            # tests
```

`--profile` defaults to `deepseek-flash` (Codex sessions in `~/.codex/sessions`).
`--harness codex|claude-code` overrides the profile's harness. If the sandbox
forbids multiprocessing sockets, add `--workers 1`. See `--help` for the rest.

## Configuration

- `config/models.json`: model profiles (model facts: prices, context window,
  threshold range, model-name filter) and harnesses (how logs are collected
  and how the trigger is set). To add a model, copy a profile and change its
  prices, window and labels; the threshold step stays 2000.
- `config/pages.json`: all page text, in a shared layer, a harness layer and a
  profile layer, each in English and Chinese. One template in `src/render.py`
  renders every page.

## Output and deployment

```text
artifacts/threshold-chart.html   Landing page (also written as index.html)
artifacts/<profile>.html         One chart page per model
artifacts/result.json            DeepSeek Flash results (published, kept as is)
artifacts/curves.csv
artifacts/<profile>/result.json  Results of the Claude profiles
artifacts/<profile>/curves.csv
```

Cloudflare Pages publishes `artifacts/` and copies `threshold-chart.html` to
`index.html` for the production root; no dashboard change is needed.

## Repository layout

```text
config/       models.json, pages.json
data/         Sanitized DeepSeek compaction samples
docs/         Methodology and statistics
src/          analysis, harnesses, profile loader, renderer, entry point
tests/        Standard-library unit tests
artifacts/    Generated site and machine-readable results
```

## Privacy

Raw session logs (`~/.codex/sessions`, `~/.claude/projects`) are read but never
copied. Generated files hold aggregate counts, fitted coefficients, curves and
sanitized compaction samples: no session IDs, paths, prompts or message
content. Review generated files before publishing results from another machine.
