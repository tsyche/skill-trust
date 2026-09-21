---
name: skill-trust
description: Trust-scoring framework for interactive skills. Invoke to configure manifests, view trust reports, or run the setup wizard. Other skills call into this for event logging and end-of-run summaries.
allowed-tools: Read, Write, Edit, Bash, AskUserQuestion
model: haiku
metadata:
  model-tier: low
---

# skill-trust

Empirical trust scoring for interactive skills. Tracks user outcomes (accept/modify/reject/cancel) to measure reliability over time and determine readiness for autonomous execution.

## Invocation

- `/skill-trust` — show trust dashboard (all configured skills)
- `/skill-trust help` / `/skill-trust --help` — list available commands and brief descriptions
- `/skill-trust configure <skill-name>` — run guided setup wizard for a skill's manifest
- `/skill-trust report <skill-name>` — detailed report for one skill
- `/skill-trust recalc <skill-name> --weights modified=0.7` — preview impact of config changes without applying
- `/skill-trust export <skill-name>` — generate summary blob for marketplace contribution

---

## Mode: Help

Display available commands:

```
skill-trust — Empirical trust scoring for interactive skills

Commands:
  /skill-trust              Dashboard: trust scores for all configured skills
  /skill-trust help         This help text
  /skill-trust --help       This help text
  /skill-trust configure X  Guided setup wizard (create or edit a skill's manifest)
  /skill-trust report X     Detailed report: scores, trends, version history, export readiness
  /skill-trust recalc X     What-if: preview impact of weight/threshold changes
  /skill-trust export X     Generate summary blob for shared marketplace contribution

Configured skills:
  {list skill names from all trust-manifest.json files found}

Getting started:
  /skill-trust configure <skill-name>   to create a manifest for a new skill
```

Steps:
1. Find all `trust-manifest.json` files: `find ~/.claude/skills -name "trust-manifest.json"`
2. List their parent directory names as "Configured skills"
3. Display the help text above

## Scorer CLI

All scoring is done by the tested scorer, never by the model doing arithmetic on the log:

```bash
python3 "${SKILL_TRUST_SCORER:-$HOME/Repos/skill-trust/src/skill_trust/scorer.py}" MANIFEST ~/.claude/skill-trust/events.jsonl
```

Prints status (`READY` / `NOT YET` / `NEW` / `UNREACHABLE`), Wilson lower bound (all-time and rolling), abandonment rate, and per-version scores. Override the location with `SKILL_TRUST_SCORER`.

## File locations

```
~/.claude/skills/{skill-name}/
  SKILL.md
  trust-manifest.json           # per-skill config (lives WITH the skill, shareable)

~/.claude/skill-trust/
  events.jsonl                  # append-only event log (local, per-user, never committed)
```

Manifests live with their skill because they're part of the skill's definition — risk profile, weights, thresholds. They ship with the skill to a marketplace.

Events live separately because they're personal, append-only, and would cause merge conflicts if shared.

---

## Mode: Dashboard (no args)

Show a summary table of all skills that have trust-manifest.json files:

```
Skill                    | Rolling (n) | All-time (n) | Threshold | Status
-------------------------|-------------|--------------|-----------|-------
pr-comments-resolve      | 91% (20)    | 85% (47)     | 90%       | READY
qa-verify                | 78% (15)    | 78% (15)     | 85%       | NOT YET
```

Steps:
1. Find all `trust-manifest.json` files: `find ~/.claude/skills -name "trust-manifest.json"`
2. Run the scorer CLI once per manifest
3. Display the table from its output (rolling = `rolling-lower`, all-time = `wilson-lower`)

---

## Mode: Configure (wizard)

Guided setup for a new or existing manifest.

**Bootstrap (first direct use):** if `~/.claude/skill-trust/` doesn't exist yet, create it now (`mkdir -p ~/.claude/skill-trust`) before writing any manifest or event — this is the one path where creating the directory is correct, since the user just explicitly asked to set up trust tracking. (Contrast with the install gate in `references/integration.md`, which governs *other* skills checking for the framework — there, absence means "skip silently," never "create it.")

Steps:
1. Check if `~/.claude/skills/{skill-name}/trust-manifest.json` exists
2. If exists, show current config and ask what to change
3. If new, walk through:
   - **Risk profile** — low / medium / high (sets sensible defaults)
     - low: threshold 0.80, rolling window 15, modified weight 0.7, autonomy threshold 0.85
     - medium: threshold 0.90, rolling window 20, modified weight 0.5, autonomy threshold 0.92
     - high: threshold 0.95, rolling window 30, modified weight 0.3, autonomy threshold 0.97
   - **Outcome weights** — show defaults, allow overrides
   - **Export settings** — min_events_since_last (default 30), snooze_days (default 7)
   - **Collective trust** — min_contributors (default 3), min_total_events (default 100)
   - **Notes** — freeform context about why these weights make sense
4. If existing events exist for this skill, show what the score would be under new config vs. old config
5. Confirm and write the manifest

### Manifest schema

```json
{
  "skill": "pr-comments-resolve",
  "version": "v1",
  "risk_profile": "medium",
  "individual_trust_rules": {
    "threshold": 0.90,
    "rolling_window": 20,
    "outcome_weights": {
      "accepted": 1.0,
      "modified": 0.5,
      "rejected": 0.0,
      "cancelled": null,
      "timeout": null
    }
  },
  "export": {
    "min_events_since_last": 30,
    "min_stability": 0.05,
    "snooze_days": 7,
    "last_prompted": null,
    "last_exported": null
  },
  "collective_trust_rules": {
    "autonomy_threshold": 0.92,
    "min_contributors": 3,
    "min_total_events": 100,
    "contributor_weight": "rejection_rate"
  },
  "notes": "..."
}
```

---

## Mode: Report

Detailed breakdown for a single skill.

Steps:
1. Read `~/.claude/skills/{skill-name}/trust-manifest.json`
2. Run the scorer CLI for the score, rolling score, per-version scores, and abandonment rate
3. Add what the CLI doesn't cover by reading events.jsonl (filtered to this skill):
   - Outcome distribution (X% accepted, Y% modified, Z% rejected, W% cancelled)
   - Trend: last 5 invocations' outcomes
   - Export readiness: events since last export, stability metric
4. Display report

---

## Mode: Recalc (what-if)

Preview impact of weight/threshold changes without modifying the manifest.

Steps:
1. Read current manifest
2. Apply overrides from args (e.g., `--weights modified=0.7 --threshold 0.85`)
3. Recompute by running the scorer CLI against a temp copy of the manifest with the overrides applied
4. Show side-by-side: current config score vs. proposed config score
5. If proposed score crosses the threshold: warn explicitly — "This change would qualify the skill for autonomous execution recommendation. Apply? [y/n]"
6. If confirmed, update the manifest (bump `updated` date in notes)

---

## Mode: Export

Generate a summary blob for contributing to a shared marketplace repo.

Steps:
1. Read manifest and events for the skill
2. Compute summary:
   ```json
   {
     "skill": "pr-comments-resolve",
     "contributor": "{git user.name or prompt}",
     "period": "{first_event_date}/{last_event_date}",
     "n": 34,
     "score": 0.87,
     "rejection_rate": 0.12,
     "version_scores": {"v1": 0.82, "v2": 0.91},
     "exported_at": "2026-05-13T10:00:00Z"
   }
   ```
3. Show the summary to the user for review
4. If approved, write to a local file (future: open PR to marketplace repo)
5. Update manifest: set `last_exported` to now

---

## Scoring algorithm

The scorer CLI is authoritative. It scores the **Wilson lower bound** of the weighted mean, so a perfect record on a small sample doesn't read as trustworthy:

```
mean  = sum(weight[outcome]) / count(events where weight is not null)
score = wilson_lower(mean, n)
```

- A gate the window can't clear even with a perfect record reports `UNREACHABLE`
- Events with `null`-weighted outcomes are excluded entirely (don't count in denominator)
- Rolling score uses the last `rolling_window` non-null events
- All-time uses every non-null event ever logged

### Collective scoring (for marketplace aggregation)

- Each contributor's events are scored independently → one score per person
- Contributors' scores are averaged with equal weight regardless of event volume
- Weighted by rejection rate (skepticism calibration): `contributor_influence = base_weight * (1 + rejection_rate)`. A skeptic's acceptance is a stronger trust signal.
- Version regression detection: if a skill version drops collective score > 10 points, flag in the collective report

---

## Event log format

One JSON object per line in `~/.claude/skill-trust/events.jsonl`:

```json
{"ts": "2026-05-12T15:30:00Z", "skill": "pr-comments-resolve", "version": "v1", "outcome": "accepted", "context": {"pr": 296, "repo": "project-billing", "source": "thread", "file": "foo.py"}}
```

### Fields

| Field | Required | Description |
|-------|----------|-------------|
| ts | yes | ISO 8601 timestamp |
| skill | yes | Skill name (matches manifest filename's parent dir) |
| version | yes | Skill version at time of event (from manifest) |
| outcome | yes | One of: `accepted`, `modified`, `rejected`, `cancelled`, `timeout` |
| outcome_detail | no | Optional finer granularity (e.g., `modified-wording` vs `modified-intent`) — ignored by base scoring, surfaced in detailed reports |
| context | no | Freeform object with useful metadata (PR number, repo, source type, file path, etc.) |

### Outcome definitions

| Outcome | When to log |
|---------|-------------|
| `accepted` | User accepted the suggestion as-is, no edits |
| `modified` | User edited the suggestion before accepting (partial agreement) |
| `rejected` | User explicitly said no / chose a different action |
| `cancelled` | User bailed out of the skill mid-run (Ctrl+C, closed, etc.) |
| `timeout` | Skill prompted but user never responded |

### Suggested-run strike

When the agent **proactively suggests** running a skill (the user didn't ask for it unprompted) and that run produces **zero findings / zero value** — an audit that fixes nothing and flags nothing, a review that finds no issues, a comment-resolver with no unresolved comments — log a `rejected` event (a strike) and skip any quality prompt. Rationale: the score should track the quality of the agent's *judgment about when to suggest the skill*, not just output quality. A skill that's constantly suggested but comes back empty is being over-suggested; the strike pulls its score down until that judgment improves.

This applies **only** to agent-suggested runs. A zero-findings run the *user* explicitly requested is a clean bill of health, not a strike — log `accepted`. Skills where this fits and should state the rule in their own trust step: audit-docs, audit-tests, audit-skills, code-review, simplify, consolidate-skills, and pr-comments-resolve (no unresolved comments).

---

## Export prompting (built into integrated skills)

After the end-of-run trust summary, check whether to prompt for export:

1. Count events since `last_exported` (or all events if never exported)
2. If count >= `min_events_since_last`:
   - Check score stability: variance of last `rolling_window` scores < `min_stability`
   - Check snooze: if `last_prompted` is set and within `snooze_days`, skip
3. If all conditions met, show:
   ```
   You have {N} new trust events for {skill} since your last export.
   This period: {score}% | Previous export: {prev_score}%
   Export summary to shared marketplace? (yes / not now / snooze)
   ```
   - `yes` → run export flow
   - `not now` → do nothing, don't update last_prompted
   - `snooze` → set last_prompted to now (won't ask again for snooze_days)

---

## Integration instructions for other skills

Skill authors wiring up trust tracking for a new skill: load [`references/integration.md`](references/integration.md) for the install gate, event-logging one-liner, the explicit-question pattern, and the end-of-run summary template. Not needed for `/skill-trust`'s own Dashboard/Report/Recalc/Export/Configure modes above.

---

## Rules

- **Never modify events.jsonl entries** — append only. If an event was logged incorrectly, append a correction event with context explaining the override.
- **Manifest changes don't rewrite history** — they only change how data is scored/interpreted.
- **The wizard must show impact before applying** — never silently change a threshold.
- **Autonomy is never automatic** — `meets_autonomy_criteria` is a recommendation flag, not an action trigger. Humans collectively decide.
- **Exclude cancelled/timeout from scoring by default** — they're ambiguous. Include only if explicitly configured with non-null weights.
- **Version tracking matters** — always log the skill version so you can detect regressions.
- **Export is always opt-in** — prompt, don't push. Never export without user review and approval.
- **One vote per contributor** — in collective scoring, volume doesn't buy influence. A user with 200 events gets the same weight as one with 20.
