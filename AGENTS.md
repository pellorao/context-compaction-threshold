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

- Threshold step is 2K for every profile, and every grid point is a multiple of 2000 (so hovering shows round values); a test checks it. `autoCompactWindow` is always shown as whole thousands (trigger + buffer rounded to the nearest 1K). Every profile's grid starts above its post-compaction context (a trigger at or below it compacts on every request); the analysis refuses a grid that does not, and the page says so. The axis maximum is the largest effective trigger (largest settable window minus the measured buffer) from an authoritative source. If it cannot be verified, ask the user; never choose a value.
- The upper chart's axis shows percent change of cost relative to the central curve at the largest threshold, spanning only the cost line and its band with at most five equal round steps, both ends on ticks and 0 inside, so differences between triggers stay visible. Pages never show US dollars (no secondary line, price caption or dollar text, in either language); absolute cost per 1M billed tokens with the historical billing mix lives only in `result.json` and the docs. Counts are normalized the same way (per 1M billed tokens) and time is a share of model request time (below); a number that scales with the amount of history is never shown as a result, only as a description of the data (sessions, requests, hours).
- Prices and context windows come from official sources, never from memory. An unknown fact becomes a question, not a guess.
- Moving or refactoring must not change numbers: compare hashes of `result.json` and the rendered pages before and after.
- Do not run an analysis in a way that overwrites committed `data/` files unintentionally; send results elsewhere with `--output-dir`. A run rewrites the logged rows (`log-`, `transcript-` sources) of its `compactions.json` from the current logs (with `--output-dir` it writes that file into the output directory, not into `data/`; `borrowed-` rows are built in memory from the donor and never stored) and keeps hand-timed rows, so Codex hand rows stay as measured; a log row with the same input, cached and output tokens as a hand row is dropped.

## Time share and model time

- Pages have two stacked charts with the same x axis and width: the upper one is cost only; the lower one is time, where the orange share line and the purple total-time line share ONE percent axis, from just below the lowest total-time change (at least 0) to a fixed top of 20% (`time_axis_max`), curves clipped above. The orange line is a share of model request time: an agent's compaction-request seconds divided by its own total request seconds (compaction requests included), pooled across sessions as sum over sum. Every request carries its observed duration (`Request.seconds`) and the context it really had (`Request.observed_input`); replay and bootstrap carry both, a replayed request's duration is the observed one plus the fitted context slope times the context difference, and modelled compactions add seconds to numerator and denominator. Model time (request plus compaction seconds) relative to the largest threshold is still computed and documented but drawn as the purple line of the lower chart (the text layer's `legend_total` is the switch), computed live from the slider speed with a band from the slope interval and the compaction lo/central/hi rows. DeepSeek's context slope is not fitted from the logs (they mix cold and warm requests) but measured in a controlled run (Codex, deepseek-flash high, 384 requests in 4 night-time blocks, 16K to 900K; warm OLS is central, Theil-Sen the low end, OLS 90th percentile the high end; no daytime-peak run) and set in the profile as `request_slope` (central, low, high; the one place to update). Tool execution and user time are never included. There is no idle-gap or wall-clock concept; do not reintroduce one.
- Request duration per harness is defined in `docs/methodology.md` ("Timing from the logs"); keep both harnesses and both languages of that section in step with the code.
- Codex summary size `G` is the constant mean (harness setting `summary_grows_with_input` false); Claude Code uses `G = g0 + g1 * C`.

## Page text

Page text lives only in `config/pages.json`, in English and Simplified Chinese, in plain human tone. Chinese text has no English sentences mixed in. Do not hard-code text in `src/render.py` (the two language names on the switch are the only exception). The page body says only what the reader needs to act; evidence and justification (sources, reasons, fit details) go in the collapsed details section or in `docs/methodology*.md`.

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
- Commit only when the user asks; push `main` right after every commit (user 2026-11-12), so every commit publishes the site. If `git push` disconnects, retry with `git -c http.version=HTTP/1.1 push`.
