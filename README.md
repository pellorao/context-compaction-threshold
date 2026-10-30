English | [简体中文](README.zh-CN.md)

# DeepSeek Best Compaction Threshold

An empirical calculator for the trade-off between DeepSeek token cost and
context-compaction time. It replays real DeepSeek Codex sessions, fits a cost
and latency model from measured compactions, expands the observed request
workload with a block bootstrap, and publishes the result as a standalone
HTML chart.

[View the live report](https://deepseek-compaction-threshold.pages.dev/)

The chart has no universal winner. The useful threshold depends on how much
working context a user needs and how much compaction cost and delay they are
willing to accept.

## What is measured

- Only Codex sessions using `deepseek-flash` are included.
- Requests are deduplicated by response ID.
- Explicit smoke/probe/test sessions are excluded.
- Calibration sessions can be excluded with repeated `--exclude-thread`
  arguments.
- The latest post-compaction tail of an active analysis thread can be included
  with `--active-thread`.
- The current calibration file contains nine real compactions: six from real
  session context shortened by semantic trimming and three native compactions.

## Method

For every request, the cost model is:

```text
Q(x, c, y) = p_m * ((1-c) + alpha*c) * x + p_o * y
alpha = p_c / p_m
rho = p_o / p_m
```

The compaction-time model is:

```text
t_c = a*(C-K) + G/v
```

where `C` is compaction input, `K` is the reusable cached prefix, `G` is
summary output, `a` is prefill time per uncached token, and `v` is effective
summary-generation speed. The public page exposes `v` as the
“server output speed” slider while keeping cost unchanged.

The threshold curve is computed in three stages:

1. Replay each real session exactly to obtain the observed staircase curve.
2. Circular-block-bootstrap each session's real request transitions, using
   blocks of eight requests. A fixed seed creates 100 workloads.
3. Replay every threshold on every resampled workload and average the results.

There is no final-curve smoothing step. The smooth line is a Monte Carlo
expectation over request-growth patterns actually present in the sessions.

## Quick start

The project has no third-party Python dependencies.

```bash
python3 src/generate.py
```

To reproduce a report for a specific active session:

```bash
python3 src/generate.py \
  --active-thread <active-thread-id> \
  --exclude-thread <calibration-thread-1> \
  --exclude-thread <calibration-thread-2>
```

Restricted sandboxes may block Python multiprocessing sockets. In that case
run outside the sandbox or use the slower sequential mode:

```bash
python3 src/generate.py --workers 1
```

Outputs:

```text
artifacts/result.json
artifacts/curves.csv
artifacts/threshold-chart.html
```

## Repository layout

```text
data/compaction_trials.json   Sanitized measured compaction samples
src/analysis.py               Session loading, fitting, replay, and bootstrap
src/render.py                 Self-contained HTML renderer
src/generate.py               Command-line entry point
artifacts/                    Generated report and machine-readable results
tests/                         Standard-library unit tests
```

Run the tests with:

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
```

## Privacy

Raw Codex JSONL files are read from `~/.codex/sessions` but are never copied
into this repository. Generated JSON contains aggregate counts, fitted
coefficients, curves, and sanitized calibration samples. It does not include
session IDs, local paths, working directories, prompts, tool output, or
message content.

Review generated artifacts before publishing a report built from a different
machine.

## Caveats

- The result is conditional on this workload distribution and DeepSeek pricing.
- The block bootstrap expands observed patterns; it cannot invent genuinely
  new workload behavior.
- The compaction sample is small. The shaded range represents observed cache
  prefix and summary-length variation, not a formal confidence interval.
- Re-run the analysis when sessions, prices, or server throughput materially
  change.

