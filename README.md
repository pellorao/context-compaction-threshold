English | [简体中文](README.zh-CN.md)

# Context Compaction Threshold

An empirical calculator for the trade-off between token cost and
context-compaction time. It replays real agent sessions, fits a cost and
latency model from measured compactions, expands the observed workload with a
block bootstrap, and publishes a static site: a landing page where you pick a
model, and one chart page per model (DeepSeek Flash, GPT-6.1 Sol, GPT-6.1
Terra and GPT-6 Luna on Codex, plus Claude Opus 5.5 and Claude Sonnet 5.5 on
Claude Code). Pages are in English and Simplified Chinese.

[View the live report](https://context-compaction-threshold.pages.dev/)

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
python3 src/generate.py --render-only                           # rebuild the pages from data/*/*/result.json
python3 -m unittest discover -s tests -p 'test_*.py'            # tests
```

`--profile` defaults to `deepseek-flash` (Codex sessions in `~/.codex/sessions`).
`--harness codex|claude-code` overrides the profile's harness. If the sandbox
forbids multiprocessing sockets, add `--workers 1`. See `--help` for the rest.

The three GPT Codex profiles use only sessions started in the previous 14 days.
Ordinary requests and compaction calibration use the same selected sessions.
Use `--snapshot-at 2026-10-31T21:11:07Z` to anchor that window for a reproducible
run against a frozen session snapshot; otherwise it is anchored at run time.
Their cost curves use fixed API token weights without a long-context surcharge,
following the subscription convention agreed for this project.

## Configuration

- `config/models.json`: model profiles (model facts: prices, context window,
  threshold range, model-name filter) and harnesses (how logs are collected
  and how the trigger is set). To add a model, copy a profile and change its
  prices, window and labels; the threshold step stays 2000.
- `config/pages.json`: all page text, in a shared layer, a harness layer and a
  profile layer, each in English and Chinese. One template in `src/render.py`
  renders every page.

## Output and deployment

Git holds only data. Everything about one (harness, profile) pair lives in
`data/<harness>/<profile>/`, and the paths are derived from the two names:

```text
data/<harness>/<profile>/compactions.json   Sanitized compaction samples (calibration input)
data/<harness>/<profile>/result.json        Analysis result (the only input of the pages)
```

`artifacts/` holds only generated pages, is git-ignored and is never committed:
`artifacts/index.html` (landing page) and `artifacts/<profile>.html` (one chart
page per model). A profile has one default harness, so `<profile>.html` is
unambiguous.

Edit page text in `config/pages.json` and layout in `src/render.py`, then
regenerate; do not edit generated HTML. The landing page keeps compact cards
with the harness at the top right and a muted, regular-weight cheapest-trigger
line. Card descriptions and Claude window-setting rows are omitted. Both
languages must fit below 900px of content height at a 1920px viewport width.

Cloudflare Pages builds the site on every push to `main` with
`python3 src/generate.py --render-only` and publishes `artifacts/`. The build
needs only Python 3 and the committed `result.json` files: no sessions, network
or packages. Python 3.8 or newer is enough. Local Wrangler is not required;
use the Cloudflare API for Pages configuration changes.

`compactions.json` holds one row per measured compaction: `name`, `source`,
`input_tokens`, `cached_tokens`, `output_tokens` and `seconds`, numbers only. For
Codex every analysis run refreshes the compactions read from the logs
(`log-auto`); DeepSeek also keeps its 9 hand-timed samples. For Claude Code every analysis run
rewrites them from the transcripts (`transcript-auto` or `transcript-manual`),
and the fit reads them back. Claude Sonnet 5.5 has too few compactions of its
own and borrows the Opus ones when it is fitted; the borrowed rows are not
copied into its file. Pass `--compactions FILE` to fit from another samples file.

Private raw sessions stay out of the repository, for example under the
git-ignored `.tmp/sessions/<harness>/<profile>/`; pass them with
`--session-root`. The default root stays the harness's own (`~/.codex/sessions`,
`~/.claude/projects`).

## Repository layout

```text
config/       models.json, pages.json
data/         Committed data by harness and profile: compactions.json, result.json
docs/         Methodology and statistics
src/          analysis, harnesses, profile loader, renderer, entry point
tests/        Standard-library unit tests
artifacts/    Generated pages only (git-ignored, built at deploy time)
```

## Privacy

Raw session logs (`~/.codex/sessions`, `~/.claude/projects`) are private; frozen
local snapshots stay under the git-ignored `.tmp/`. Committed and generated files hold aggregate counts, fitted coefficients, curves and
sanitized compaction samples: no session IDs, paths, prompts or message
content. Review generated files before publishing results from another machine.
