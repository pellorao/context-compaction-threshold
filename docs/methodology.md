English | [简体中文](methodology.zh-CN.md)

# Methodology and statistics

This page holds the fixed rules of the project and the data statistics of each profile. The README stays short and points here. Statistics come from the generated `result.json` files. The Claude Code transcripts on the maintainer's machine keep growing, so a new run gives slightly different numbers.

## Data layout

Everything is stored per (harness, profile) pair, with paths derived from the two names:

| What | Path |
|---|---|
| Sanitized compaction samples (calibration input), committed | `data/<harness>/<profile>/compactions.json` |
| Analysis result (the only input of the pages), committed | `data/<harness>/<profile>/result.json` |
| Chart pages, generated at deploy time, git-ignored | `artifacts/index.html`, `artifacts/<profile>.html` |
| Raw private sessions (not in the repository; example location) | `.tmp/sessions/<harness>/<profile>/`, passed with `--session-root` |

The statistics below are the contents of those `result.json` files. Git holds only the data under `data/`; Cloudflare Pages builds the pages with `python3 src/generate.py --render-only`, which reads only the committed `result.json` files (the session logs are private).

### Rebuild the published pages

Run `python3 src/generate.py --render-only` from a checkout. The six committed results, model profiles, bilingual text and renderer reproduce the landing page and all six model pages without raw sessions, a new fit or network access. The 14-day filter runs only during analysis: rendering uses the saved snapshot and does not age out its data as time passes.

The sanitized compaction files preserve calibration inputs; they do not contain the ordinary-request histories needed to rerun analysis. For a new analysis, use the private frozen sessions and their manifests, including the recorded analysis-session exclusion, together with `--snapshot-at`. A timestamp fixes the session-start selection window, not the contents of a live log directory. Keep new results separate with `--output-dir`, which also keeps the run's compaction samples in that directory; use `--compactions` to select a saved calibration instead. Raw sessions, private manifests and generated HTML are never committed.

## Fixed rules

### Threshold grid

- A threshold is the context size, in tokens, at which a compaction triggers.
- The grid step is **2000 tokens for every profile**. The published DeepSeek curve already used 2000; it is a project rule, not a per-model choice. A test checks it.
- The grid must start above the profile's post-compaction context: a trigger at or below it compacts again on every request, which distorts the cost axis. The analysis refuses such a grid, and a test checks the published results.
- The cost axis spans only the range of the curves and their shaded band, extended on both ends to a tick (at most five equal round steps), rather than starting at $0, so differences between triggers stay visible. Read the tick labels before comparing heights across models.
- The grid sits on even multiples of the step, so hovering shows round values such as 200K and 300K. The grid minimum is the smallest multiple of 2K at or above the smallest trigger that can be set. The grid maximum is the largest multiple of 2K at or below the **maximum effective trigger = maximum setting - measured buffer**. A test checks that every grid point is a multiple of 2000. If that maximum cannot be verified from an authoritative source for a model, the profile's axis maximum is left unset and the question goes to the maintainer.
- DeepSeek Flash on Codex keeps its published axis, 64K to 900K. Codex has no window-plus-buffer setting, so its page only shows the trigger.

### Codex subscription profiles (GPT-6.1 Sol, GPT-6.1 Terra, GPT-6 Luna)

- Each profile has its own requests and compaction calibration, with exact model-prefix filtering and the existing exclusions and response-ID deduplication. Sessions without compactions remain part of the ordinary workload.
- `session_max_age_days: 14` selects sessions whose recorded start is within the 14 days ending at the analysis snapshot. An older session is excluded in full even if resumed recently. Selection happens before response-ID deduplication and applies to ordinary requests, compaction samples, the ordinary-request time fit and post-compaction measurements alike. Missing start times and starts after the snapshot are excluded; file modification times are never used.
- `--snapshot-at` accepts an ISO timestamp with a timezone; without it, the snapshot is the current UTC time. All three published profiles use the same frozen snapshot. The inclusive start bounds are recorded as `snapshot.session_selection` in each result.
- The maintainer confirmed **872,000 tokens × 95% = 828,400** as the effective upper trigger for these profiles. The grid ends at **828K**, rounding the upper bound down to a 2K grid point; it starts at **64K** for Luna and Sol and at **70K** for Terra (see the grid floor rule above). This is the agreed Codex boundary, not the API catalog's context-window size or a claim that the default Codex window is 872K. The public [configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference) defines `model_context_window` and `model_auto_compact_token_limit` separately.
- Relative costs use the official API standard input/cache-read/output weights below, held constant at every context length. The project uses the agreed subscription convention of no long-context surcharge; it does not estimate included subscription allowance or purchased-credit consumption. A uniform rate multiplier cancels in relative cost, whereas a context-dependent surcharge would change the curve. Codex records no separate cache writes here; the unused cache-write fields in these profiles equal the plain input weight, not an API cache-write tariff.
- Each model uses its own timed compactions. Summary size is their constant mean, and post-compaction context and uncached input are the medians of the first ordinary requests after compaction, before chaining. Ordinary-request context slopes are fitted from these sessions, not borrowed from DeepSeek's controlled measurement. The existing Codex min/max compaction scenarios, block size 8, 100 bootstrap replicates and seed 20261031 apply.

### Claude Code trigger (Opus 5.5, Sonnet 5.5)

The setting is `autoCompactWindow` (global, or per model under `modelSettings`).

| Fact | Value | Source |
|---|---|---|
| Allowed window | 100K to 1M tokens | Claude Code settings reference, `modelSettings.autoCompactWindow` ("a number of tokens from 100000 to 1000000"); model configuration page; the setting description inside the installed Claude Code 2.1.316 |
| Model context window | Opus 5.5 and Sonnet 5.5: 1M | claude-api skill, Current Models table (1M context, 128K max output); Claude Code model configuration page (Opus 4.7 and later, Sonnet 5 and later run the 1M window by default) |
| Window cap | The effective window is the smaller of the setting and the model window | Model configuration page (Claude Code caps it at the model's context window) |
| Buffer | 33K | Documentation: "Sessions auto-compact at about 967K tokens by default" with a 1M window. Installed Claude Code: trigger = window - min(max output, 20K) - 13K = window - 33K. Logs: median automatic compaction input of 267.9K (Opus) and 267.8K (Sonnet) under the 300K window set for the logged sessions, i.e. a measured buffer of 32.1K (Opus) and 32.2K (Sonnet) |

Consequences:

- Smallest effective trigger = 100K - 33K = 67K. Largest = 1M - 33K = 967K.
- Grid: **68K, 70K, ... 966K** (the even multiples of 2K inside that range). The window to set is `autoCompactWindow = trigger + 33000`, so it is an odd multiple of 1000 (101000, 103000, ... 999000), which the setting accepts. Triggers are always shown as whole K ("116K", never "116,000 tokens"), because the grid is on even K. Pages and tooltips show the window for the chosen trigger as the literal setting value to copy (for example `153000`), always as a whole number of thousands: trigger + buffer is rounded to the nearest 1K (half up), so a measured, non-round buffer can never produce decimals.
- The buffer is the same for both models, because it depends on the model only through `min(max output, 20K)` and both have 128K max output. The logs cannot record the window in force at each compaction, so the measured buffer assumes the 300K window that was set for the logged sessions.
- Not verifiable here: whether every plan can use a 1M window with these two models. The documentation does not restrict it, and windows of 300K and below are confirmed by the logs.

### Cost axis: cost per 1M billed tokens

The cost axis of every profile is normalised so that charts stay comparable however much history was analysed.

- Billed tokens of the real history `N` = plain input + cache writes (5 minutes and 1 hour) + cache reads + output, summed over all included, deduplicated requests. It is one constant per profile, computed from the history and stored in `result.json` as `snapshot.billed_tokens`, with the split in `snapshot.billing_mix`.
- Plotted cost at a threshold = total replay cost at that threshold / (`N` / 1,000,000). The divisor is **not** the token count of the replay at that threshold, which changes with the threshold and would distort the curve.
- The reference million tokens therefore has the real billing mix of the sessions. All cost numbers use it: chart, tooltip, quick picks and the key numbers below. `result.json` keeps the total dollars (`cost_usd_off_peak`) and the normalised value (`cost_per_million_tokens`) side by side.
- Counts are normalised the same way. The tooltip shows compactions per 1M billed tokens (the compaction count of the replay divided by `N` / 1,000,000), with 5 decimals: the smallest value on any profile's grid is 0.00096 (Sonnet at 966K) and the largest 0.72 (Sonnet at 68K), so 5 decimals keep at least two significant digits everywhere. A test checks it. Time is shown as a share of model request time (see "Time share" below), which does not scale with the history. Every other number on the pages is a ratio, a price, a fitted coefficient or a description of the data (sessions, requests, hours).
- Compaction requests are not part of `N` (Claude Code transcripts do not contain them, and Codex compaction requests are removed, see below). They are part of the replay cost.
- DeepSeek Flash is normalised the same way. Its first published curve was in total dollars of a smaller history and had no token totals, so it was recomputed from the Codex sessions.
- Display unit: the pages show cost relative to the central cost at the largest threshold of the axis (`cost / cost_max - 1`, in percent, 0% at the largest trigger). The pages never show dollars; the absolute dollars per 1M tokens stay in `result.json` and in this document. Bands are relative to the same central baseline, not to their own scenario's value at the largest trigger.

### Prices

Costs are in units of the plain input price, then converted to USD. Prices are per million tokens.

| Profile | Input | Cache write 5 min | Cache write 1 h | Cache read | Output | Source |
|---|---|---|---|---|---|---|
| deepseek-flash | $0.15 | $0.15 | $0.15 | $0.003 | $0.60 | DeepSeek off-peak list prices, as used by the first published version of this project |
| claude-opus-5-5 | $4 | $5 | $8 | $0.20 | $20 | claude-api skill: Current Models table ($4 / $20); prompt-caching Economics (writes 1.25x for 5 minutes and 2x for 1 hour, reads 0.05x on Opus 5.5) |
| claude-sonnet-5-5 | $2 | $2.50 | $4 | $0.20 | $10 | claude-api skill: Current Models table ($2 / $10, cache reads $0.20); same write multipliers |
| gpt-6.1-sol | $2 | n/a | n/a | $0.10 | $10 | [Official model page](https://developers.openai.com/api/docs/models/gpt-6.1-sol) |
| gpt-6.1-terra | $1 | n/a | n/a | $0.05 | $5 | [Official model page](https://developers.openai.com/api/docs/models/gpt-6.1-terra) |
| gpt-6-luna | $0.10 | n/a | n/a | $0.01 | $0.50 | [Official model page](https://developers.openai.com/api/docs/models/gpt-6-luna) |

For the three GPT profiles, alpha is 0.05, 0.05 and 0.1, and rho is 5 for all three. For the other profiles, the ratio alpha (cache read / input) is 0.02, 0.05 and 0.1. The ratio rho (output / input) is 4, 5 and 5.

### Which sessions and requests count

Codex (`~/.codex/sessions`):

- Sessions whose provider is the profile's provider or whose model name starts with a profile prefix.
- Requests are deduplicated by response ID.
- Sessions whose working directory contains `smoke`, `probe` or `test` are excluded, and so are the sessions used to time compactions (`--exclude-thread`). `--active-thread` excludes the analysis session and adds its latest stretch after its last compaction.
- Codex logs each real compaction as a compaction request immediately followed by a `compacted` record. That request is removed from the session (it is not part of `N`, and the replay models compactions itself), and the stretches before and after are chained into one uncompacted request stream as for Claude Code (see below). Without this, the sudden drop of the context at a real compaction made the replayed context negative and every cost negative.
- A session is a candidate when its provider is the profile's provider or its model matches, but it is only included if every model it used starts with a profile prefix. Two sessions with `deepseek-v4-pro` (62 requests) matched by provider only and are excluded as `other-model`: that model has other prices.
- Each request has a duration (see "Time share" and "Timing from the logs" below). Real compactions of the analysis session and of the other included sessions become compaction samples; the sessions used for hand timing are excluded from the samples so that no compaction is counted twice.

Claude Code (`~/.claude/projects/**/*.jsonl`):

- Only `assistant` entries whose model starts with the profile's prefix: `claude-opus-5-5`, `claude-sonnet-5-5`. Other versions, for example `claude-opus-4-8`, are excluded because their prices differ.
- Requests are deduplicated globally by `message.id`. A response streamed over several lines counts once, with the largest `output_tokens`. Message IDs repeat across files (forks and resumes), so the dedupe spans all files.
- Subagent transcripts are included. They compact with the same mechanism and carry most of the compactions (168 of 261 for Opus).
- One transcript file is one session. Files with no matching request are excluded.
- Cache-write tokens are priced by each session's real 5-minute and 1-hour write mix, which gives the session's uncached-token price multiplier.
- Each request has a duration (see "Time share" and "Timing from the logs" below), for the main conversation and for subagents alike.

### Time share

The orange line is the **share of model request time spent compacting** (the orange line in the lower time chart, which shares one axis with the total-model-time line: from just below the lowest total-time change up to a fixed 20%, curves clipped above). For every agent alike, main or subagent, it is that agent's compaction-request seconds divided by that agent's total request seconds (all its model requests, compaction requests included). It has nothing to do with the agents it calls, with idle gaps, with tool execution time or with how long the session lasted. Across sessions the shares are pooled: the sum of the compaction seconds divided by the sum of the request seconds, never an average of per-session shares.

- Every request keeps the duration it had in the real session (`Request.seconds`). The block bootstrap resamples each request transition together with its duration, so a replicate has its own total request time.
- A replayed compaction adds its modelled seconds to the numerator and to the denominator. Real compactions are removed from the request stream (they are not requests of the replay), so the denominator holds only the ordinary requests plus the modelled compactions.
- Ordinary requests keep their observed duration adjusted for the replayed context (next section), so the request seconds `R_T` depend on the threshold.
- `time_share = compaction seconds / (R_T + compaction seconds)`. `result.json` stores both sums in every curve row (`compaction_seconds`, `request_seconds`) and the real history's request seconds in `snapshot.request_seconds`. The pages divide the slider-adjusted compaction seconds by the same replicate-mean `R_T`.
- Validation against the real history: at the trigger the real automatic compactions used, the replay share matches the observed share. Opus: 261 real compactions took 15,431 s of 424,853 s of request plus compaction time (3.63%), and the exact replay at a 266K trigger gives 3.56%. Sonnet: observed 2.64%, exact replay 2.25% at 266K (24 compactions, so noisier). For DeepSeek the observed 4.82% is not comparable (the replay gives 5.5% at 266K), because the 25 timed compactions include those of the analysis session, which the replay only joins as a tail.
- The idle-gap rule (gaps over 300 s) and the work-time concept were removed together with agent time versus wall clock: nothing in the analysis depends on them any more.

### Request duration, model time and relative units

An ordinary request takes longer the more context it carries. The replay models this, and total model time is computed as a second measure. It is drawn as the purple line of the time chart on every page (see the Result bullet).

- Fit: per profile, ordinary least squares of the observed request duration on the context the request really had (`Request.observed`, the context before chaining and resampling moved it) and its output tokens, with an intercept, over all included requests (compaction requests are not in the stream; requests whose duration was unknown and filled with the median are included, 82 of 45,356 Opus requests). The context coefficient `s` (seconds per context token) is stored as `fitted_model.request_seconds_per_context_token`, with the fit's intercept, output coefficient and R2 beside it.
- Interval: the same fit is repeated on every block-bootstrap replicate (same seed, block and replicate count as the curves); the interval is the 10th to 90th percentile of those slopes (`..._low`, `..._high`). The slope is weakly determined (Sonnet's low end is about zero), so it is a band, not a point. DeepSeek's slope is the exception: it is not fitted from the logs but set in the profile (`request_slope` in `config/models.json`: central, low, high), from a controlled measurement (below). It replaces the fitted slope and its bootstrap quantiles in the replay and in `fitted_model.request_seconds_per_context_token*`; `request_slope_source` in `result.json` says `controlled` or `log-fit`, and the log-fitted slope stays in `request_seconds_per_context_token_log_fit` for reference.
- Replay: a request replayed at context `x_T` instead of the observed `x_obs` takes `observed seconds + s * (x_T - x_obs)`. Summed over a workload this is `request_base_seconds + s * context_shift_tokens`, both stored per curve row, so `R_T` for any slope follows linearly. Rows store `request_seconds` (central slope) and `request_seconds_slope_lo`, `request_seconds_slope_hi`. A single replayed request can come out below zero at a low trigger; the sum is what the metrics use, so no floor is applied (a floor would also break the linearity). The same slope is used above the largest observed context (287K for Opus, 268K for Sonnet), where it is extrapolated.
- Total model time: `W_T = R_T + compaction seconds` (the compaction seconds are the output part rescaled by the speed slider plus the prefill part). Tool execution and user time are not included: they do not change with the trigger. It is in the analysis output and the tables below, and the pages draw it as the purple line of the time chart.
- Relative units: the chart shows `cost_T / cost_max - 1` in percent (the upper chart's axis spans only the cost line and its band; `W_T / W_max - 1` is drawn on Claude pages as the purple line of the lower time chart, same baseline and slider speed, its band is the min/max over the slope interval and the compaction low/central/high rows, same on DeepSeek), where the baseline is the central curve at the largest threshold (966K for Claude, 900K for DeepSeek) at the same slider speed.
- Bands: cost uses the low and high cost scenarios. Model time and time share use every combination of the three compaction scenarios (low, central, high rows) with the three slopes (low, central, high) and take the minimum and maximum. They are divided by the central baseline `W_max`, so a band at the largest trigger is not zero-width.
- Result: see the tables below. Pages draw it as the purple line in the time chart and show it on the pick cards and in the tooltip, recomputed live from the slider speed. At the measured speed: total model time rises quickly as the trigger drops below 150K (at 100K about +10% for Opus and +17% for Sonnet, bands entirely above 0) and stays within about ±2.5% of the largest trigger above 200K. DeepSeek pages draw it too, with the slope from a controlled measurement: 384 requests through Codex on `deepseek-flash` at high effort (4 blocks run in two night-time sessions, each block 2 sweeps over 8 context sizes from 16K to 900K, 1 cold and 5 warm requests per size; 320 warm, 64 cold). The warm requests (the normal case, cache hit about 99.9%) give 0.96 s per 100K tokens (OLS, intercept 1.90 s, R2 0.185; bootstrap 10th to 90th percentile 0.75 to 1.18; per-block OLS 0.96, 1.55, 0.47, 0.86); the robust Theil-Sen slope is 0.31; cold requests give 2.38 (1.96 to 2.82). Slow requests (at least twice the median of their size, 48 of 320) cluster by context size (permutation p < 0.001) and much less by sweep or time (p = 0.05): long contexts are more often slow, so the mean (OLS) is the central value, the typical request (Theil-Sen) the low end and the OLS 90th percentile the high end. The profile uses central 0.96, low 0.31 and high 1.18. All runs were at night local time, so the daytime peak is not covered. The slope fitted on the session logs (1.30 s, intercept -0.83 s, poor fit at small contexts) mixed cold and warm requests, so it is not used. The result depends strongly on this slope. The three numbers live only in `request_slope`. Details: Opus: the slope is small against a 9.0 s mean request, and model time is within a few percent of the largest trigger from 200K up (minimum near 364K). Sonnet: model time is nearly flat from 300K up. DeepSeek: the slope is large against a 4.5 s mean request, so large triggers make every request slow; the central model-time curve has its minimum at 136K (-33.8%).

### Timing from the logs, side by side

Both harnesses give the duration of every normal request and of every real compaction. The two methods are laid out in the same rows. The compaction rows feed the time model `t_c`; the request rows give the denominator of the time share.

| | Codex (`~/.codex/sessions`) | Claude Code (`~/.claude/projects`) |
|---|---|---|
| Compaction: start | The later of the current turn's `task_started` and the last `token_count` event more than 1 s before `compacted` (use whichever exists if only one is available). This excludes the user's wait when a turn compacts before its first ordinary request. It is the end of the request before the compaction, or the start of the turn that holds the compaction. Events within 1 s of the record belong to the compaction request itself. | Not needed: Claude Code writes the duration itself. |
| Compaction: end | The `compacted` record's timestamp. | The `compact_boundary` entry, carrying `compactMetadata.durationMs`. |
| Compaction: seconds | End minus start. | `durationMs / 1000`. |
| Compaction: input `C` and cached part | The usage record of the compaction request (the `token_usage_record` right before `compacted`): `input_tokens` and `cached_input_tokens`. | `compactMetadata.preTokens` for `C`. The compaction request is not in the transcript: the cached part is `preTokens` minus an uncached tail (`preTokens` minus the context of the last request before the boundary, at least 0). |
| Compaction: summary size `G` | `output_tokens` of the same usage record, exact. | Estimated from the summary text (the user entry marked `isCompactSummary`): tokens per CJK character and per other character, fitted on plain answers (text only, thinking subtracted). |
| Compactions used | All compactions of the included sessions and of the analysis session (a duplicate is dropped by `compaction_response_id`). A compaction that was also timed by hand keeps its hand timing. | All `compact_boundary` entries, deduplicated by timestamp and `preTokens`. |
| Compactions left out | Those of smoke or test sessions, of sessions on another model and of the hand-timing sessions (they are the hand-timed rows); those without either an earlier `token_count` or a current `task_started`. | Those with no request before, no duration or size, or no summary text. |
| Request: start | The timestamp of the last log record before the request that is not the model's own output: a user or developer message or a tool output. For the first request after a compaction, the `compacted` record. | The timestamp of the nearest `user` or `assistant` entry on the `parentUuid` chain above the first line of the response. `attachment` and `system` entries (hooks, reminders) are skipped: they are written asynchronously and carry unrelated times. |
| Request: end | The request's `token_usage_record` timestamp (the same instant as its `token_count`). | The last streamed line of the same `message.id`. |
| Request: unknown or not positive | Takes the median of the known durations (0 requests in the current data). | The same (82 of 45,293 Opus requests, 0.2%: the first line of a transcript has no parent; Sonnet 0). |
| Request: validation | 2,933 requests: none negative, median 2.8 s, 5th to 95th percentile 1.1 s to 14.2 s, maximum 65 s. | Opus: none negative after skipping attachments (3.3% were negative and 4.3% zero when attachments were used as the start), median 5.7 s, 5th to 95th percentile 2.2 s to 23.9 s, maximum 973 s; 18 requests above 300 s (2.1% of request time) are kept. Sonnet: median 4.9 s, 5th to 95th percentile 1.9 s to 19.0 s, maximum 257 s. |

Known limits:

- Timestamps are the times the harness wrote the records, with millisecond resolution; a duration includes any client-side gap between a record and the request leaving or arriving.
- Codex compactions start at the later of the previous `token_count` and the current `task_started`. This excludes the user's wait before a turn, while a little client-side time before the compaction request may remain. For the 9 compactions that were timed both by hand and in the logs, the hand timing is 0.2 s to 2.7 s longer (about 1.5 s on average), a client-side offset of the hand method. The hand rows are kept as measured.
- Codex input and cached part come from the compaction request's own usage, not from the request before it (the two differ by up to about 20K tokens for the same compaction, and the own usage is what the model processed). The hand-timed rows used the same fields.
- Claude Code: if a response interleaves with tool execution, its last streamed line can be later than the real end of the response, which lengthens that request. The summary size is an estimate (Sonnet's estimator rests on 33 plain answers).
- In both harnesses the request seconds include the model's thinking time and any network retry.

### How compactions are found and calibrated

- Codex: `data/codex/deepseek-flash/compactions.json` holds the 9 hand-timed samples (source `native` or `session-derived`, kept as measured) and the compactions read from the logs (source `log-auto`, numbers only). Every analysis run replaces the `log-auto` rows and keeps the hand rows. Real compactions are also removed from the request stream and the stretches around them are chained.
- Claude Code: the samples are written to `data/claude-code/<profile>/compactions.json` on every analysis run (source `transcript-auto` or `transcript-manual`; numbers only, no ids, timestamps, paths or text) and read back for the fit. `system` entries with subtype `compact_boundary`, carrying `compactMetadata` (trigger, `preTokens`, `durationMs`). The summary is the following user entry marked `isCompactSummary`. Boundaries are deduplicated by timestamp and `preTokens`. A compaction is dropped from calibration if there is no request before it, no duration or size, or no summary text.
- The compaction request itself is not in the transcripts. Its input is the whole context before the compaction: all cache reads except a small uncached tail (`preTokens` minus the last request's context), which is priced as a cache write at the session's multiplier.
- Summary tokens are estimated from the summary text. Output tokens of plain answers (text only, thinking tokens subtracted) are regressed on the number of CJK characters and of other characters (when the plain answers contain no CJK text, one rate is fitted for every character).
- Compaction time `t_c = a * C + G / v` is fitted without intercept on the compactions (`C` is the whole compaction input on Claude Code and its uncached part on Codex, `G` the summary tokens). On Claude Code summary tokens follow `G = g0 + g1 * C`. On Codex `G` is constant, the mean of the timed summaries (harness setting `summary_grows_with_input`): with the 25 samples the correlation between `G` and `C` is 0.17, the fitted slope (0.0020 tokens per token, standard error 0.0024) is not different from zero, and a leave-one-out test favours the constant (RMSE 1,611 tokens against 1,753 for the linear fit; a log-linear fit gives 1,619, no better). The earlier linear model (9 hand-timed samples) overestimated `G` at large contexts: it put the 888K compaction at 9.9K summary tokens against 4.5K measured.
- Post-compaction context and its uncached part are the medians of the first request after each compaction (Claude Code), or the measured values (DeepSeek).
- Real automatic compactions fire at one level (about 267K for Claude Code, about 300K for Codex), so higher triggers are never observed. Each session's segments split by real compactions are chained into one uncompacted request stream: a later segment continues from the previous context by one median increment, with the median uncached part. Above about 267K the curves are therefore extrapolated.
- If a model has fewer than 50 compactions of its own (harness setting `min_fit_compactions`) and the profile names a `borrow_calibration` profile, the fit uses its own compactions plus the donor's, read from the donor's `compactions.json` (the borrowed rows are a fit-time rule and are not copied into the model's own file). The donor's durations are multiplied by the **median**, over the model's own compactions, of measured seconds divided by what the donor fit predicts for that compaction. The median is used so that one unusually slow compaction barely moves the scale. The page and the statistics below label this. Without a donor the run stops.

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
- The shaded range uses the 10th to 90th percentile of the measured compaction variation for the Claude profiles and the minimum to maximum for DeepSeek. The time bands also include the 10th to 90th percentile of the request-time slope over the replicates.
- The bootstrap curve lies below the exact replay of the real sessions (stored as `exact_curves` in `result.json`): by 0.2% to 6.2% for Opus and 1.4% to 12.7% for Sonnet, and between 7.0% below and 1.5% above for DeepSeek, over the whole grid. Read the shape and the position of the minimum more than the absolute numbers.

## Statistics per profile

### Data

| | deepseek-flash | claude-opus-5-5 | claude-sonnet-5-5 |
|---|---|---|---|
| Harness | codex | claude-code | claude-code |
| Independent sessions | 26 plus the active tail | 555 (20 main, 535 subagent) | 217 (5 main, 212 subagent) |
| Deduplicated requests | 2,933 | 45,356 | 9,074 |
| Request time (sum of request durations) | 13,322 s (3.7 h) | 409,422 s (113.7 h) | 65,772 s (18.3 h) |
| Requests with no usable duration (median used) | 0 | 82 | 0 |
| Excluded | smoke or test 6, empty 1, analysis 5, calibration 8, other model 2 | 604 files with no matching request | 942 files with no matching request |
| Compactions found | 9 hand-timed; 19 read from the logs (16 in the analysis session, 3 already hand-timed) | 261 (auto-subagent 168, auto-main 90, manual-main 4) | 24 (auto-subagent 24) |
| Compactions used | 25 (9 hand-timed, 16 from the logs) | 260 (1 dropped: no request before) | 24 own, plus 260 borrowed from Opus |
| Largest observed context | 887,611 | 286,634 | 267,868 |
| Median automatic compaction input | n/a | 267,893 | 267,874 |
| Measured buffer (300K window minus median) | n/a | 32.1K (33K used) | 32.2K (33K used) |
| Mean uncached-token price multiplier | 1.0 | 1.279 | 1.267 |
| Context right after a compaction, uncached part | 17,623 / 13,152 | 51,862 / 27,968 | 51,068 / 32,116 |

### Billing mix of the real history

Billed tokens `N` and their split. This is the mix of the reference million tokens in the cost axis. For the Claude models plain input is below 0.01%: nearly all fresh input is billed as cache writes. DeepSeek has no cache-write price.

| | deepseek-flash | claude-opus-5-5 | claude-sonnet-5-5 |
|---|---|---|---|
| Billed tokens `N` | 619,721,155 | 6,768,613,994 | 1,104,236,808 |
| Cache reads | 98.50% | 96.57% | 95.06% |
| Cache writes, 5 minutes | 0.00% | 2.78% | 4.32% |
| Cache writes, 1 hour | 0.00% | 0.39% | 0.09% |
| Plain input | 1.22% | 0.00% | 0.00% |
| Output | 0.28% | 0.26% | 0.53% |

### Fitted model

| | deepseek-flash | claude-opus-5-5 | claude-sonnet-5-5 |
|---|---|---|---|
| Seconds per input token `a` | 6.08e-6 (uncached tokens) | 4.34e-5 (all tokens) | 5.26e-5 (all tokens) |
| Seconds per output token | 0.00647 | 0.00605 | 0.00661 |
| Summary speed `v` | 154.5 tokens/s | 165.4 tokens/s | 151.2 tokens/s |
| Summary tokens | `G` = 3,930 (constant) | `g0 + g1 * C` = 6,061 + 0.00677 C | 6,084 + 0.00656 C |
| R2, time model (both / output only / input only) | 0.96 / 0.95 / -0.94 | 0.73 / 0.69 / -0.01 | 0.44 / 0.41 / -0.01 |
| Request duration: seconds per 100K context tokens, central (10th to 90th percentile; DeepSeek: controlled measurement, low and high) | 0.96 (0.31 to 1.18) | 0.27 (0.16 to 0.37) | 0.20 (0.00 to 0.44) |
| Request duration: R2 of the fit, mean request | 0.57, 4.5 s | 0.25, 9.0 s | 0.63, 7.2 s |
| Cached part of a compaction input: central (low, high) | 6,272 tokens (3,456; 273,408) | all but a tail of 1,702 (7,695; 373) | all but a tail of 1,748 (7,802; 377) |
| Summary estimator | n/a | 1.19 tokens per CJK char, 0.54 per other char, 1,406 messages | 1.52 and 0.37, 33 messages (small sample) |
| Borrowed calibration | no | no | donor claude-opus-5-5, time scale x1.10 (median ratio) |

The summary estimator of Sonnet rests on 33 plain answers only, so its rates are noisy. One of Sonnet's 24 own compactions took 285 s, against 37 to 102 s for the other 23. With the ratio of totals as the scale, the ratio of totals would give a time scale of x1.30, driven mostly by that one compaction, so the scale is the median of the per-compaction ratios: x1.10. The outlier still sits in the pooled fit as one of the 24 own compactions, which is why the time-model R2 (0.44) is lower and the summary speed (151.2 tokens/s) differs from Opus.

### Key results (central curve, default summary speed)

"Window" is the `autoCompactWindow` to set: trigger + 33K. Cost is relative to the largest trigger (966K Claude, 900K DeepSeek), with dollars per 1M billed tokens in parentheses. Model time is request plus compaction seconds relative to the largest trigger, with the band over the compaction scenarios and the slope interval. Share is the share of model request time spent compacting.

Cheapest trigger, and the cheapest trigger that keeps compaction under a share of model request time (DeepSeek has no window to set):

| Profile | Limit | Trigger | Window | Cost vs largest | Model time vs largest | Share |
|---|---|---|---|---|---|---|
| deepseek-flash | none | 124K | n/a | -28.9% ($0.0064) | -33.6% | 14.8% |
| deepseek-flash | 5% | 282K | n/a | -24.7% ($0.0068) | -28.9% | 5.0% |
| deepseek-flash | 3% | 414K | n/a | -19.0% ($0.0073) | -22.3% | 3.0% |
| deepseek-flash | 2% | 536K | n/a | -14.3% ($0.0077) | -16.2% | 2.0% |
| deepseek-flash | 1% | none | n/a | n/a | n/a | n/a |
| claude-opus-5-5 | none | 120K | 153000 | -46.7% ($0.330) | +5.4% | 12.0% |
| claude-opus-5-5 | 5% | 220K | 253000 | -40.6% ($0.368) | -1.2% | 5.0% |
| claude-opus-5-5 | 3% | 306K | 339000 | -33.9% ($0.410) | -2.2% | 3.0% |
| claude-opus-5-5 | 2% | 408K | 441000 | -27.0% ($0.452) | -2.3% | 2.0% |
| claude-opus-5-5 | 1% | 668K | 701000 | -13.3% ($0.537) | -1.4% | 1.0% |
| claude-sonnet-5-5 | none | 104K | 137000 | -30.3% ($0.278) | +15.1% | 15.4% |
| claude-sonnet-5-5 | 5% | 186K | 219000 | -24.8% ($0.300) | +3.2% | 4.9% |
| claude-sonnet-5-5 | 3% | 240K | 273000 | -20.6% ($0.317) | +1.4% | 3.0% |
| claude-sonnet-5-5 | 2% | 302K | 335000 | -16.3% ($0.334) | +0.7% | 2.0% |
| claude-sonnet-5-5 | 1% | 416K | 449000 | -10.5% ($0.357) | +0.1% | 1.0% |

Curves at selected triggers (cost and model time vs the largest trigger, with the band in brackets; share of request time compacting):

| Profile | Trigger | Cost | Model time | Share |
|---|---|---|---|---|
| deepseek-flash | 100K | -27.7% (-51.0 to -23.3) | -32.1% (-47.1 to +12.6) | 19.5% |
| deepseek-flash | 150K | -28.4% (-48.6 to -25.8) | -33.7% (-45.1 to +1.5) | 11.9% |
| deepseek-flash | 200K | -27.3% (-45.6 to -25.5) | -32.4% (-41.8 to -2.8) | 8.1% |
| deepseek-flash | 300K | -24.0% (-38.2 to -22.9) | -28.0% (-35.1 to -5.6) | 4.6% |
| deepseek-flash | 600K | -12.3% (-18.3 to -11.8) | -13.8% (-16.7 to -4.0) | 1.7% |
| deepseek-flash | 900K | 0% (-3.9 to +0.3) | 0% (-12.3 to +4.9) | 1.01% |
| claude-opus-5-5 | 100K | -45.9% (-48.5 to -42.3) | +10.1% (+2.5 to +17.5) | 15.9% |
| claude-opus-5-5 | 150K | -45.7% (-46.9 to -44.1) | +1.9% (-1.8 to +5.5) | 8.6% |
| claude-opus-5-5 | 200K | -42.3% (-43.0 to -41.3) | -0.6% (-2.9 to +1.6) | 5.7% |
| claude-opus-5-5 | 300K | -34.3% (-34.6 to -33.9) | -2.2% (-3.1 to -1.3) | 3.1% |
| claude-opus-5-5 | 600K | -16.4% (-16.5 to -16.3) | -1.7% (-2.9 to -0.6) | 1.1% |
| claude-opus-5-5 | 966K | 0% (-0.0 to +0.1) | 0% (-1.9 to +1.8) | 0.68% |
| claude-sonnet-5-5 | 100K | -30.2% (-32.0 to -27.7) | +16.8% (+8.1 to +25.3) | 16.6% |
| claude-sonnet-5-5 | 150K | -27.8% (-28.5 to -26.9) | +5.8% (+2.0 to +9.5) | 7.5% |
| claude-sonnet-5-5 | 200K | -23.6% (-23.9 to -23.1) | +2.6% (+0.4 to +4.6) | 4.3% |
| claude-sonnet-5-5 | 300K | -16.4% (-16.6 to -16.2) | +0.7% (-0.1 to +1.4) | 2.0% |
| claude-sonnet-5-5 | 600K | -5.9% (-6.0 to -5.9) | -0.2% (-0.8 to +0.5) | 0.44% |
| claude-sonnet-5-5 | 966K | 0% (-0.0 to +0.0) | 0% (-0.9 to +1.1) | 0.23% |

The central model-time curve has its minimum at 364K for Opus (-2.4%), at 608K for Sonnet (-0.2%, practically flat from 300K up) and at 136K for DeepSeek (-33.8%, close to the cheapest trigger).

Triggers whose cost is within a given margin of the minimum:

| Margin | Opus | Sonnet | DeepSeek |
|---|---|---|---|
| 1% | 104K to 140K | 92K to 126K | 106K to 158K |
| 2% | 98K to 152K | 88K to 134K | 98K to 192K |
| 5% | 90K to 176K | 80K to 162K | 74K to 262K |

Ends of the axis: Opus costs $0.430 at a 68K trigger (33.5% of request time compacting) and $0.620 at 966K (0.68%). Sonnet costs $0.325 at 68K (37.0%) and $0.399 at 966K (0.23%). DeepSeek costs $0.0068 at 64K (31.3%) and $0.0090 at 900K (1.01%), so no trigger on its axis keeps compaction under 1% of request time.

## Recent Codex subscription profile statistics

All three snapshots are anchored at **2026-10-31 21:11:07 UTC**, with session starts from **2026-10-17 21:11:07 UTC through that instant**, inclusive. These statistics are separate from the original three models' published snapshots; their results are not recomputed. Ordinary requests and compactions use the same selected cohort; under the existing rule the active analysis session supplies compaction calibration only, with no ordinary-request tail included in this snapshot.

| | gpt-6.1-sol | gpt-6.1-terra | gpt-6-luna |
|---|---|---|---|
| Independent sessions | 137 | 12 | 58 |
| Ordinary requests after deduplication | 38,991 | 10,907 | 16,736 |
| Ordinary request time | 184.3 h | 14.9 h | 42.2 h |
| Timed compactions | 346 | 66 | 269 |
| Billed tokens in ordinary history | 5,969,263,954 | 1,558,705,812 | 2,157,860,960 |
| Cache read / plain input / output | 96.30% / 3.33% / 0.37% | 98.44% / 1.34% / 0.22% | 94.91% / 4.41% / 0.68% |
| Largest ordinary request input | 458,260 | 449,760 | 245,127 |
| Post-compaction context / uncached input | 33,717 / 20,854 | 68,834 / 58,054 | 48,783 / 35,809 |

None has separately billed cache writes or ordinary requests needing a median duration fill. Sol's calibration includes compactions of the active analysis session, so the sessions supplying calibration are not exactly the ordinary-request session counts above. Every fit uses its own compactions, with no borrowed calibration.

| | gpt-6.1-sol | gpt-6.1-terra | gpt-6-luna |
|---|---|---|---|
| Mean summary tokens (constant G) | 6,033.0 | 2,146.8 | 2,527.9 |
| Compaction seconds per uncached input token | 6.3516e-05 | 8.7303e-05 | 2.6787e-05 |
| Compaction seconds per output token | 0.02314 | 0.01287 | 0.00871 |
| Summary speed, tokens/s | 43.2 | 77.7 | 114.8 |
| Compaction time fit R2 | 0.588 | 0.694 | 0.851 |
| Ordinary request: seconds per additional 100K context tokens (low to high) | 4.021 (3.747–4.227) | 0.638 (0.466–0.751) | 0.163 (0.050–0.279) |
| Ordinary request time fit R2 | 0.644 | 0.514 | 0.909 |
| Compaction cached prefix: median (min to max) | 200,000 (7,680–466,560) | 199,296 (11,904–449,536) | 199,552 (7,168–244,992) |

At the default summary speed, the rows below show the central curve's cheapest trigger, and its cheapest trigger subject to a compaction-time share limit. Cost and total model time are relative to 828K. Absolute amounts per million billed tokens are normalized costs under the fixed API weights, not subscription spending or allowance consumption. The pages display relative costs only.

| Profile | Share limit | Trigger | Relative cost | Normalized USD / 1M billed tokens | Model time change | Compaction share |
|---|---|---|---|---|---|---|
| gpt-6.1-sol | none | 86K | -59.1% | 0.14131 | -28.4% | 28.11% |
| gpt-6.1-sol | 5% | 320K | -39.2% | 0.21013 | -29.0% | 4.99% |
| gpt-6.1-sol | 3% | 470K | -26.3% | 0.25460 | -20.4% | 2.99% |
| gpt-6.1-sol | 2% | 622K | -15.2% | 0.29305 | -12.0% | 2.00% |
| gpt-6.1-sol | 1% | — | — | — | — | — |
| gpt-6.1-terra | none | 120K | -59.5% | 0.06045 | -20.1% | 9.45% |
| gpt-6.1-terra | 5% | 168K | -57.0% | 0.06420 | -21.7% | 4.90% |
| gpt-6.1-terra | 3% | 246K | -49.3% | 0.07576 | -19.7% | 2.98% |
| gpt-6.1-terra | 2% | 398K | -34.2% | 0.09829 | -14.2% | 2.00% |
| gpt-6.1-terra | 1% | — | — | — | — | — |
| gpt-6-luna | none | 92K | -62.8% | 0.01369 | +7.0% | 12.33% |
| gpt-6-luna | 5% | 166K | -58.2% | 0.01539 | -0.7% | 4.94% |
| gpt-6-luna | 3% | 252K | -49.5% | 0.01861 | -2.1% | 2.99% |
| gpt-6-luna | 2% | 382K | -36.8% | 0.02327 | -2.1% | 1.99% |
| gpt-6-luna | 1% | — | — | — | — | — |

828K exceeds the observed contexts of all three models, so that part of each curve depends on extrapolation; the largest ordinary-request inputs are listed above. Terra has only 12 independent sessions; 100 block-bootstrap replicates do not increase that count. Reasoning effort and service modes retain the mix in the logs rather than having separate pages, so these durations are not a model-speed ranking. Terra's measured post-compaction context is 68,834 tokens, so its grid starts at 70K, the first 2K point above it: a trigger at or below that size compacts on every request.
