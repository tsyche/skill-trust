# skill-trust

[![ci](https://github.com/tsyche/skill-trust/actions/workflows/ci.yml/badge.svg)](https://github.com/tsyche/skill-trust/actions/workflows/ci.yml)

**tl;dr:** Trust scoring for interactive LLM skills (Claude Code skills, but the
idea is portable). A deterministic Python scorer turns accept/modify/reject logs
into a Wilson lower-bound score, so a perfect score on six runs doesn't read as
"trustworthy." Includes the skill definition that logs the events.

## Quick start

```bash
uv run --with pytest pytest -q
python3 src/skill_trust/scorer.py examples/trust-manifest.json examples/events.sample.jsonl
```

```text
demo-skill: NOT YET
  n=14  mean=85.7%  wilson-lower=60.1%  rolling-lower=49.0%
  abandoned runs: 22% (4/18)  malformed lines: 0
  by version: 1.0.0: 86% (n=14)
```

## What the scorer does

| Behavior | Why |
|---|---|
| Scores the **Wilson lower bound**, not the mean | 6/6 accepted is a 61% lower bound, not 100% |
| Reports `UNREACHABLE` when a gate can't be cleared | 20/20 perfect only reaches 83.9%, so a 0.90 gate at window 20 never passes |
| Reconciles `opened` events into an **abandonment rate** | Tracks failures a log written only at run end can't see |
| Collapses `v1` / `1.0` / `1.0.0` into one version | Otherwise per-version regression checks split one version in two |
| Excludes `cancelled` / `timeout` from the score | Ambiguous outcomes; reported separately, never silently counted |
| Skips and counts malformed lines | One corrupt line shouldn't take down the report |

Statuses: `READY`, `NOT YET`, `NEW` (fewer events than the window), `UNREACHABLE`.

## Design note: the eval system that couldn't record failure

The first version was prose an LLM interpreted at runtime, with the "compute the
rolling score" step done by a model doing arithmetic on a JSONL file. Measuring
the live data turned up two problems that no amount of statistics fixes:

- **The sample was censored by construction.** The log line was written *after*
  an interaction completed. An agent that has stopped running can't log "the user
  gave up," so rejections and cancellations were unloggable. The result was
  hundreds of events, ~99% accepted, and zero recorded failures: precise
  statistics on a sample that couldn't contain the answer.
- **The gate was sometimes mathematically unreachable.** Threshold and window
  were chosen independently. With a window of 20, no run of accepts can produce a
  lower bound of 0.90. Nothing said so, so the skill just sat at NOT YET forever.

Fixes: write an `opened` event with a `run_id` at skill entry, so a run with no
terminal event within 24h is inferred abandoned (no harness hooks needed), move
the arithmetic into tested code, and have the scorer flag gates that can't pass.

Why Wilson and not a bootstrap: when every observation is 1.0, resampling gives a
zero-width interval, which is false confidence. Wilson accounts for `n`
regardless of observed variance.

## Event schema

One JSON object per line. `run_id` is optional but enables abandonment tracking.

```json
{"ts": "2026-01-01T12:00:00Z", "skill": "demo-skill", "version": "1.0.0", "outcome": "accepted", "run_id": "r1"}
```

Outcomes: `opened` (run start, unscored), `accepted`, `modified`, `rejected`,
`cancelled`, `timeout`. Weights and gates live in a per-skill
[`trust-manifest.json`](examples/trust-manifest.json).

## Layout

- `src/skill_trust/scorer.py`: the scorer and CLI
- `tests/`: pytest suite
- `skill/`: the Claude Code skill (`SKILL.md` plus event-logging integration guide)
- `examples/`: synthetic manifest and events (not real usage data)

## Known limits

- `skill/SKILL.md` dashboard/report/recalc call the scorer CLI, but export and
  the configure wizard are still prose. No integrated skill emits `opened` events
  yet, so abandonment shows `n/a` until they do.
- Nothing yet validates that scores predict downstream quality. That meta-eval is
  the open problem.
- Event logging depends on the calling skill remembering to do it.
