English | [简体中文](methodology.zh-CN.md)

# Methodology and statistics

This page holds the fixed rules of the project and the data statistics of each profile. The README stays short and points here. Statistics come from the generated `result.json` files. The Claude Code transcripts on the maintainer's machine keep growing, so a new run gives slightly different numbers.

## Fixed rules

### Threshold grid

- A threshold is the context size, in tokens, at which a compaction triggers.
- The grid step is **2000 tokens for every profile**. The published DeepSeek curve already used 2000; it is a project rule, not a per-model choice. A test checks it.
- The cost axis always starts at $0 and is never truncated, so curves and models can be compared by eye.
- The grid minimum is the smallest trigger that can be set. The grid maximum is the **maximum effective trigger = maximum setting - measured buffer**. If that maximum cannot be verified from an authoritative source for a model, the profile's axis maximum is left unset and the question goes to the maintainer.
- DeepSeek Flash on Codex keeps its published axis, 64K to 900K. Codex has no window-plus-buffer setting, so its page only shows the trigger.

### Claude Code trigger (Opus 5.5, Sonnet 5.5)

The setting is `autoCompactWindow` (global, or per model under `modelSettings`).

| Fact | Value | Source |
|---|---|---|
| Allowed window | 100K to 1M tokens | Claude Code settings reference, `modelSettings.autoCompactWindow` ("a number of tokens from 100000 to 1000000"); model configuration page; the setting description inside the installed Claude Code 2.1.316 |
| Model context window | Opus 5.5 and Sonnet 5.5: 1M | claude-api skill, Current Models table (1M context, 128K max output); Claude Code model configuration page (Opus 4.7 and later, Sonnet 5 and later run the 1M window by default) |
| Window cap | The effective window is the smaller of the setting and the model window | Model configuration page (Claude Code caps it at the model's context window) |
| Buffer | 33K | Documentation: "Sessions auto-compact at about 967K tokens by default" with a 1M window. Installed Claude Code: trigger = window - min(max output, 20K) - 13K = window - 33K. Logs: median automatic compaction input of 267.9K (Opus) and 267.9K (Sonnet) under the 300K window set for the logged sessions, i.e. a measured buffer of 32.1K for both |

Consequences:

- Minimum trigger = 100K - 33K = **67K**. Maximum trigger = 1M - 33K = **967K**.
- Grid: 67K, 69K, ... 967K. Every grid point maps to a round window: `autoCompactWindow = trigger + 33000`, from 100000 to 1000000 in steps of 2000. Pages and tooltips show that window value for the chosen trigger.
- The buffer is the same for both models, because it depends on the model only through `min(max output, 20K)` and both have 128K max output. The logs cannot record the window in force at each compaction, so the measured buffer assumes the 300K window that was set for the logged sessions.
- Not verifiable here: whether every plan can use a 1M window with these two models. The documentation does not restrict it, and windows of 300K and below are confirmed by the logs.

### Cost axis: cost per 1M billed tokens

The cost axis of every profile is normalised so that charts stay comparable however much history was analysed.

- Billed tokens of the real history `N` = plain input + cache writes (5 minutes and 1 hour) + cache reads + output, summed over all included, deduplicated requests. It is one constant per profile, computed from the history and stored in `result.json` as `snapshot.billed_tokens`, with the split in `snapshot.billing_mix`.
- Plotted cost at a threshold = total replay cost at that threshold / (`N` / 1,000,000). The divisor is **not** the token count of the replay at that threshold, which changes with the threshold and would distort the curve.
- The reference million tokens therefore has the real billing mix of the sessions. All cost numbers use it: chart, tooltip, quick picks, CSV column `expected_cost_usd_per_million_tokens` and the key numbers below. `result.json` keeps the total dollars (`cost_usd_off_peak`) and the normalised value (`cost_per_million_tokens`) side by side.
- Compaction requests are not part of `N` (Claude Code transcripts do not contain them, and Codex compaction requests are removed, see below). They are part of the replay cost.
- DeepSeek Flash is normalised the same way. Its first published curve was in total dollars of a smaller history and had no token totals, so it was recomputed from the Codex sessions.

### Prices

Costs are in units of the plain input price, then converted to USD. Prices are per million tokens.

| Profile | Input | Cache write 5 min | Cache write 1 h | Cache read | Output | Source |
|---|---|---|---|---|---|---|
| deepseek-flash | $0.15 | $0.15 | $0.15 | $0.003 | $0.60 | DeepSeek off-peak list prices, as used by the first published version of this project |
| claude-opus-5-5 | $4 | $5 | $8 | $0.20 | $20 | claude-api skill: Current Models table ($4 / $20); prompt-caching Economics (writes 1.25x for 5 minutes and 2x for 1 hour, reads 0.05x on Opus 5.5) |
| claude-sonnet-5-5 | $2 | $2.50 | $4 | $0.20 | $10 | claude-api skill: Current Models table ($2 / $10, cache reads $0.20); same write multipliers |

The ratio alpha (cache read / input) is 0.02, 0.05 and 0.1. The ratio rho (output / input) is 4, 5 and 5.

### Which sessions and requests count

Codex (`~/.codex/sessions`):

- Sessions whose provider is the profile's provider or whose model name starts with a profile prefix.
- Requests are deduplicated by response ID.
- Sessions whose working directory contains `smoke`, `probe` or `test` are excluded, and so are the sessions used to time compactions (`--exclude-thread`). `--active-thread` excludes the analysis session and adds its latest stretch after its last compaction.
- Codex logs each real compaction as a compaction request immediately followed by a `compacted` record. That request is removed from the session (it is not part of `N`, and the replay models compactions itself), and the stretches before and after are chained into one uncompacted request stream as for Claude Code (see below). Without this, the sudden drop of the context at a real compaction made the replayed context negative and every cost negative.
- A session is a candidate when its provider is the profile's provider or its model matches, but it is only included if every model it used starts with a profile prefix. Two sessions with `deepseek-v4-pro` (62 requests) matched by provider only and are excluded as `other-model`: that model has other prices.
- Work time is the sum of the task durations the session reports. It includes the seconds of the real compactions (about 20 to 30 s each, under 3% of the long session that has them).

Claude Code (`~/.claude/projects/**/*.jsonl`):

- Only `assistant` entries whose model starts with the profile's prefix: `claude-opus-5-5`, `claude-sonnet-5-5`. Other versions, for example `claude-opus-4-8`, are excluded because their prices differ.
- Requests are deduplicated globally by `message.id`. A response streamed over several lines counts once, with the largest `output_tokens`. Message IDs repeat across files (forks and resumes), so the dedupe spans all files.
- Subagent transcripts are included. They compact with the same mechanism and carry most of the compactions (168 of 261 for Opus).
- One transcript file is one session. Files with no matching request are excluded.
- Cache-write tokens are priced by each session's real 5-minute and 1-hour write mix, which gives the session's uncached-token price multiplier.
- Work time is the sum of the gaps between consecutive matching requests of a session. Gaps longer than 300 seconds count as idle, and compaction durations are removed. Subagents running in parallel are added together, so time shares are shares of agent time, not of the wall clock.

### How compactions are found and calibrated

- Codex: a hand-measured trials file, `data/compaction_trials.json`. Real compactions inside the sessions are only used to chain the stream, not for calibration.
- Claude Code: `system` entries with subtype `compact_boundary`, carrying `compactMetadata` (trigger, `preTokens`, `durationMs`). The summary is the following user entry marked `isCompactSummary`. Boundaries are deduplicated by timestamp and `preTokens`. A compaction is dropped from calibration if there is no request before it, no duration or size, or no summary text.
- The compaction request itself is not in the transcripts. Its input is the whole context before the compaction: all cache reads except a small uncached tail (`preTokens` minus the last request's context), which is priced as a cache write at the session's multiplier.
- Summary tokens are estimated from the summary text. Output tokens of plain answers (text only, thinking tokens subtracted) are regressed on the number of CJK characters and of other characters.
- Compaction time `t_c = a * C + G / v` is fitted without intercept on the compactions (`C` is the whole compaction input, `G` the summary tokens). Summary tokens follow `G = g0 + g1 * C`.
- Post-compaction context and its uncached part are the medians of the first request after each compaction (Claude Code), or the measured values (DeepSeek).
- Real automatic compactions fire at one level (about 267K for Claude Code, about 300K for Codex), so higher triggers are never observed. Each session's segments split by real compactions are chained into one uncompacted request stream: a later segment continues from the previous context by one median increment, with the median uncached part. Above about 267K the curves are therefore extrapolated.
- If a model has fewer than 50 compactions of its own (harness setting `min_fit_compactions`) and the profile names a `borrow_calibration` profile, the fit uses its own compactions plus the donor's. The donor's durations are multiplied by the ratio of the model's own measured total time to what the donor fit predicts for them. The page and the statistics below label this. Without a donor the run stops.

### DeepSeek model update of 2026-10-17

DeepSeek updated Flash on 2026-10-17 (DeepSeek's pricing page lists it as `DeepSeek-V4.1-Flash-1017`). Checked on the Codex sessions, in aggregate:

| Period | Candidate files | Requests | Included |
|---|---|---|---|
| Before the update (2026-09-30, 2026-10-01) | 6 | 80 | none, all are smoke or test sessions |
| After the update (2026-10-30, 2026-10-31) | 42 | 3,480 | yes, minus the exclusions above |

- Every request record in both periods has the same fields (`input_tokens`, `cached_input_tokens`, `output_tokens`, `reasoning_output_tokens`, `cache_write_input_tokens`, `total_tokens`).
- The counting convention is the same in both: `cached_input_tokens` never exceeds `input_tokens` (so input includes cached tokens), `total_tokens` equals input plus output in every request, `reasoning_output_tokens` never exceeds `output_tokens` (so reasoning is part of output), `cache_write_input_tokens` is always 0, and usage is per request, not cumulative.
- The model id of the included sessions is `deepseek-flash` throughout. Only the two excluded sessions used `deepseek-v4-pro`.
- All included data therefore comes from after the update, so no per-period normalisation is needed. If sessions from both periods are mixed in a later run, the detection should use these fields and the model id, not a date.
- Prices: DeepSeek's current pricing page lists `deepseek-flash` at the off-peak $0.003 cache hit, $0.15 cache miss and $0.60 output per million tokens, equal to the profile. It does not say what Flash cost before the update. The prices of earlier data cannot be checked, but no earlier data is included. Open question for the maintainer: were the Flash prices different before 2026-10-17 (only matters if the older sessions are ever included)?

### Resampling

- Circular block bootstrap of each session's real request-to-request changes: block of **8 requests**, **100 replicates**, seed **20261031**.
- Every threshold is replayed on every replicate and the results are averaged. The final curves are not smoothed.
- The shaded range uses the 10th to 90th percentile of the measured compaction variation for the Claude profiles and the minimum to maximum for DeepSeek.
- The bootstrap curve lies below the exact replay of the real sessions (stored as `exact_curves` in `result.json`): by 1% to 6% for Opus, 3% to 13% for Sonnet and within 2.5% (above or below) for DeepSeek at the points checked. Read the shape and the position of the minimum more than the absolute numbers.

## Statistics per profile

### Data

| | deepseek-flash | claude-opus-5-5 | claude-sonnet-5-5 |
|---|---|---|---|
| Harness | codex | claude-code | claude-code |
| Independent sessions | 26 plus the active tail | 555 (20 main, 535 subagent) | 216 (5 main, 211 subagent) |
| Deduplicated requests | 2,933 | 45,170 | 8,752 |
| Work time | 25,274 s (7.0 h) | 762,635 s (211.8 h) | 137,180 s (38.1 h) |
| Excluded | smoke or test 6, empty 1, analysis 5, calibration 8, other model 2 | 603 files with no matching request | 942 files with no matching request |
| Compactions found | 9 measured (calibration); 16 real compactions inside one long session, chained | 261 (auto-subagent 168, auto-main 90, manual-main 3) | 21 (auto-subagent 21) |
| Compactions used | 9 | 260 (1 dropped: no request before) | 21 own, plus 260 borrowed from Opus |
| Largest observed context | 887,611 | 286,634 | 267,868 |
| Median automatic compaction input | n/a | 267,893 | 267,874 |
| Measured buffer (300K window minus median) | n/a | 32.1K (33K used) | 32.1K (33K used) |
| Mean uncached-token price multiplier | 1.0 | 1.279 | 1.267 |
| Context right after a compaction, uncached part | 17,623 / 13,152 | 51,854 / 27,912 | 51,254 / 32,229 |

### Billing mix of the real history

Billed tokens `N` and their split. This is the mix of the reference million tokens in the cost axis. For the Claude models plain input is below 0.01%: nearly all fresh input is billed as cache writes. DeepSeek has no cache-write price.

| | deepseek-flash | claude-opus-5-5 | claude-sonnet-5-5 |
|---|---|---|---|
| Billed tokens `N` | 619,721,155 | 6,735,705,246 | 1,051,120,196 |
| Cache reads | 98.50% | 96.56% | 94.99% |
| Cache writes, 5 minutes | 0.00% | 2.79% | 4.39% |
| Cache writes, 1 hour | 0.00% | 0.39% | 0.09% |
| Plain input | 1.22% | 0.00% | 0.00% |
| Output | 0.28% | 0.26% | 0.53% |

### Fitted model

| | deepseek-flash | claude-opus-5-5 | claude-sonnet-5-5 |
|---|---|---|---|
| Seconds per input token `a` | 2.07e-5 (uncached tokens) | 4.34e-5 (all tokens) | 4.84e-5 (all tokens) |
| Seconds per output token | 0.00597 | 0.00604 | 0.00670 |
| Summary speed `v` | 167.5 tokens/s | 165.5 tokens/s | 149.2 tokens/s |
| Summary tokens `g0 + g1 * C` | 1,633 + 0.00942 C | 6,057 + 0.00676 C | 6,057 + 0.00665 C |
| R2, time model (both / output only / input only) | 0.98 / 0.95 / 0.20 | 0.73 / 0.69 / -0.01 | 0.71 / 0.67 / -0.01 |
| Cached part of a compaction input: central (low, high) | 13,312 tokens (3,456; 13,312) | all but a tail of 1,704 (7,730; 374) | all but a tail of 1,746 (7,848; 374) |
| Summary estimator | n/a | 1.19 tokens per CJK char, 0.54 per other char, 1,381 messages | 1.52 and 0.37, 33 messages (small sample) |
| Borrowed calibration | no | no | donor claude-opus-5-5, time scale x1.11 |

The summary estimator of Sonnet rests on 33 plain answers only, so its rates are noisy.

### Key results (central curve, default summary speed)

"Window" is the `autoCompactWindow` to set: trigger + 33K. Cost is per 1M billed tokens.

| Profile | Cheapest trigger | Cost | Time share | Window |
|---|---|---|---|---|
| deepseek-flash | 116K | $0.0062 | 4.7% | n/a |
| claude-opus-5-5 | 121K | $0.331 | 6.6% | 154000 |
| claude-sonnet-5-5 | 105K | $0.280 | 7.4% | 138000 |

Cheapest trigger that keeps compaction under a share of working time (DeepSeek has no window to set):

| Limit | Opus trigger | Opus cost | Opus window | Sonnet trigger | Sonnet cost | Sonnet window | DeepSeek trigger | DeepSeek cost |
|---|---|---|---|---|---|---|---|---|
| 5% | 145K | $0.335 | 178000 | 127K | $0.282 | 160000 | 116K | $0.0062 |
| 3% | 205K | $0.360 | 238000 | 161K | $0.293 | 194000 | 226K | $0.0065 |
| 2% | 265K | $0.391 | 298000 | 195K | $0.304 | 228000 | 480K | $0.0075 |
| 1% | 435K | $0.463 | 468000 | 273K | $0.326 | 306000 | none | none |

Triggers whose cost is within a given margin of the minimum:

| Margin | Opus | Sonnet | DeepSeek |
|---|---|---|---|
| 1% | 103K to 141K | 93K to 127K | 86K to 138K |
| 2% | 99K to 151K | 89K to 135K | 70K to 154K |
| 5% | 89K to 177K | 81K to 163K | 64K to 218K |

Ends of the axis: Opus costs $0.441 at a 67K trigger (21.7% of time compacting) and $0.619 at 967K (0.39%). Sonnet costs $0.334 at 67K (22.0%) and $0.380 at 967K (0.01%). DeepSeek costs $0.0064 at 64K (8.0%) and $0.0090 at 900K (1.6%), so no DeepSeek trigger on the axis keeps compaction under 1% of working time.
