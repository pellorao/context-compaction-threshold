# Agent guide

Context Compaction Threshold: an empirical calculator that replays real agent sessions, fits a compaction cost and time model, and publishes a static site (landing page plus one bilingual chart page per model). Methods, fixed rules and per-model statistics are in `docs/methodology.md` (Chinese: `docs/methodology.zh-CN.md`); read it before changing the analysis. Python 3 standard library only, no third-party packages.

## Layout

- `config/models.json`: profiles (model facts) and harnesses (how logs are collected). `config/pages.json`: all page text.
- `src/`: `analysis.py`, `harness_*.py`, `model_profile.py`, `render.py` (one template), `generate.py` (entry point). `tests/`: unittest.
- `data/<harness>/<profile>/`: committed sources, `compactions.json` (sanitized samples) and `result.json` (the only input of the pages). Paths are derived from the pair, never configured.
- `artifacts/`: generated pages only. Git-ignored, never committed.
- `docs/methodology*.md`: rules and statistics. Keep the English and Chinese versions in step.

## Private data (`.tmp/`)

- `.tmp/` is git-ignored. Raw logs live only in `.tmp/sessions/<harness>/<profile>/`, with the analysis-data README and manifest. They hold full conversations: never commit, publish, upload or move them outside `.tmp/`, and never print their content, ids or paths in output or reports.
- Task scratch goes in `.tmp/<task>/` and is deleted when the task is done. Run `git check-ignore` on a path before writing anything private there.
- Committed and generated files hold aggregates only (numbers, fitted coefficients, curves, sanitized samples). Before every commit, grep `data/`, `docs/` and the generated pages for session ids and uuids, home paths, `.jsonl` and `sessionId`. The only expected hits are the GitHub link and the generic `~/.claude/projects/**/*.jsonl` glob in the docs.

## Fixed analysis rules

- Threshold step is 2K for every profile. The axis maximum is the largest effective trigger (largest settable window minus the measured buffer) from an authoritative source. If it cannot be verified, ask the user; never choose a value.
- The cost axis starts at 0. Cost is normalized per 1M billed tokens with the historical billing mix.
- Prices and context windows come from official sources, never from memory. An unknown fact becomes a question, not a guess.
- Moving or refactoring must not change numbers: compare hashes of `result.json` and the rendered pages before and after.
- Do not run an analysis in a way that overwrites committed `data/` files unintentionally; send results elsewhere with `--output-dir`. A Claude Code run rewrites its `compactions.json` from the current logs.

## Page text

Page text lives only in `config/pages.json`, in English and Simplified Chinese, in plain human tone. Chinese text has no English sentences mixed in. Do not hard-code text in `src/render.py`.

## Adding a profile or harness

- Profile: copy a profile in `config/models.json`; set model name prefixes, prices, window, threshold range, labels. For a harness whose logs lack compactions, add `data/<harness>/<profile>/compactions.json`; a profile with few own compactions can set `borrow_calibration`. Add its page text layer in `config/pages.json`, run the analysis, commit `data/<harness>/<profile>/`, and add the profile to the tests.
- Harness: add `src/harness_<name>.py` with a collector, register it in `src/harness.py`, add the harness in `config/models.json` and its page layer, and cover it in `tests/`.

## Validation

- `python3 -m unittest discover -s tests -p 'test_*.py'`.
- `python3 src/generate.py --render-only` in a clean copy without `.git`, `.tmp` and `artifacts/`; then `node --check` on each page script.
- The privacy grep above.

## Deploy and git

- Pushing `main` makes Cloudflare Pages run `python3 src/generate.py --render-only` and publish `artifacts/`. No Cloudflare tooling is needed for updates.
- Changing Pages settings needs the user's Pages-only API token in `~/.config/cloudflare/`; never print or copy it.
- Commit or push only when the user asks. If `git push` disconnects, retry with `git -c http.version=HTTP/1.1 push`.
