English | [简体中文](README.zh-CN.md)

# Context Compaction Threshold

This project is an empirical calculator that helps you choose when an agent should compact its context by showing the trade-off between token cost and context-compaction time.

[View the live report](https://context-compaction-threshold.pages.dev/)

The chart has no universal winner: the right threshold depends on how much working context you need to keep and how much compaction cost and delay you are willing to accept. On the live site, a landing page lets you pick a model and open its chart page (DeepSeek Flash, GPT-6.1 Sol, GPT-6.1 Terra and GPT-6 Luna on Codex, plus Claude Opus 5.5 and Claude Sonnet 5.5 on Claude Code). For Claude Code, the page also tells you which `autoCompactWindow` value to set. Every page is available in English and Simplified Chinese.

To build those curves, the calculator replays real agent sessions, fits a cost and latency model from measured compactions, expands the observed workload with a block bootstrap, and publishes the results as a static site. All fixed rules (threshold step, axis limits, prices and their sources, what counts as a session or request, how compactions are found, and bootstrap parameters) and the per-model data statistics are documented in [docs/methodology.md](docs/methodology.md).

## Quick start

To run an analysis or rebuild the site locally, you only need Python 3—there are no third-party Python dependencies.

```bash
python3 src/generate.py --profile claude-opus-5-5 --workers 30   # analyze, then rebuild the site
python3 src/generate.py --render-only                           # rebuild the pages from data/*/*/result.json
python3 -m unittest discover -s tests -p 'test_*.py'            # tests
```

When you run an analysis, `--profile` defaults to `deepseek-flash` (reading Codex sessions in `~/.codex/sessions`), and `--harness codex|claude-code` overrides the profile's default harness. If your sandbox forbids multiprocessing sockets, add `--workers 1`. See `--help` for the remaining flags.

By default, each harness reads from its own log directory (`~/.codex/sessions`, `~/.claude/projects`). To run against private raw sessions stored outside the repository—for example under the git-ignored `.tmp/sessions/<harness>/<profile>/`—pass `--session-root`.

The three GPT Codex profiles use only sessions started in the previous 14 days, and both ordinary requests and compaction calibration use that same set of selected sessions. Because a 14-day window moves with the clock, pass `--snapshot-at 2026-10-31T21:11:07Z` to anchor the window when you want a reproducible run against a frozen session snapshot; otherwise the window is anchored at run time. Their cost curves use fixed API token weights without a long-context surcharge, following the subscription convention agreed for this project.

## Configuration

Once you can run the generator, you can add models or adjust page text and layout through two configuration files and a single renderer:

- `config/models.json` defines model profiles (model facts: prices, context window, threshold range, and model-name filter) and harnesses (how logs are collected and how the trigger is set). To add a model, copy an existing profile and change its prices, window and labels; the threshold step stays 2000.
- `config/pages.json` holds all page text across a shared layer, a harness layer and a profile layer, each in English and Chinese. A single template in `src/render.py` renders every page.

To change copy or layout, edit `config/pages.json` and `src/render.py`, then regenerate; never edit the generated HTML directly. On the landing page, cards stay compact with the harness at the top right and a muted, regular-weight cheapest-trigger line. Card descriptions and Claude window-setting rows are omitted so that both languages fit below 900px of content height at a 1920px viewport width.

## Output and deployment

Running the generator separates committed analysis data from generated HTML so the site can be built and deployed without access to raw session logs.

Git holds only data. Everything for one `(harness, profile)` pair lives in `data/<harness>/<profile>/`, at paths derived from those two names:

```text
data/<harness>/<profile>/compactions.json   Sanitized compaction samples (calibration input)
data/<harness>/<profile>/result.json        Analysis result (the only input of the pages)
```

`compactions.json` holds one row per measured compaction—`name`, `source`, `input_tokens`, `cached_tokens`, `output_tokens` and `seconds`—as numbers only. How an analysis run updates that file depends on the harness: for Codex, every run refreshes the compactions read from the logs (`log-auto`), while DeepSeek also keeps its 9 hand-timed samples; for Claude Code, every run rewrites the file from the transcripts (`transcript-auto` or `transcript-manual`), and the fit reads those rows back. Because Claude Sonnet 5.5 has too few compactions of its own, it borrows the Opus samples when fitted, without copying the borrowed rows into its own file. To fit from another samples file instead, pass `--compactions FILE`.

From the resulting `result.json` files, the renderer writes the static site into `artifacts/`: `artifacts/index.html` (the landing page) and `artifacts/<profile>.html` (one chart page per model; because each profile has one default harness, `<profile>.html` is unambiguous). The `artifacts/` directory holds only generated pages, is git-ignored and is never committed.

No generated page is committed, so deployment builds from the data instead: Cloudflare Pages builds the site on every push to `main` by running `python3 src/generate.py --render-only` and publishing `artifacts/`. Because rendering reads only the committed `result.json` files, the build needs only Python 3 (Python 3.8 or newer is enough)—no sessions, network or packages. Local Wrangler is not required; use the Cloudflare API for Pages configuration changes.

## Repository layout

Together, configuration, committed data, documentation, source code, tests and build output live in six top-level directories:

```text
config/       models.json, pages.json
data/         Committed data by harness and profile: compactions.json, result.json
docs/         Methodology and statistics
src/          analysis, harnesses, profile loader, renderer, entry point
tests/        Standard-library unit tests
artifacts/    Generated pages only (git-ignored, built at deploy time)
```

## Privacy

Because session logs contain full conversations, raw data and published outputs are strictly separated. Raw session logs (`~/.codex/sessions`, `~/.claude/projects`) and any frozen local snapshots under the git-ignored `.tmp/` (see Quick start) are private. Committed and generated files hold only aggregate counts, fitted coefficients, curves and sanitized compaction samples: no session IDs, paths, prompts or message content. Always review generated files before publishing results from another machine.
