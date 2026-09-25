# Integration instructions for other skills

> Loaded on demand by `SKILL.md` for skill authors wiring up trust tracking — not needed for Dashboard/Report/Recalc/Export/Configure invocations of `/skill-trust` itself.
>
> Paths below assume Claude Code's default root (`~/.claude`). On another
> skill-hosting agent, set `SKILL_TRUST_HOME` to that agent's root (e.g.
> `~/.codex`) and substitute it in the snippets — the layout is the same:
> `<root>/skills/` plus `<root>/skill-trust/`.

Skills that opt into trust tracking need the install gate plus two additions to their SKILL.md:

## 0. Install gate (REQUIRED — check before any trust behavior)

The trust framework is **per-user and opt-in**, and a skill that integrates with it is often distributed (e.g. via a marketplace) to users who do **not** have skill-trust installed. Before any logging, prompting, or summary, the skill MUST check whether the framework is present:

```
Check whether `~/.claude/skill-trust/` exists (e.g. `[ -d ~/.claude/skill-trust ]`).
- Absent → the framework is not installed. Skip ALL trust behavior silently: no prompt,
  no event logging, no summary. Do NOT create the directory or events.jsonl.
- Present → proceed with the logging/summary below.
```

The directory's absence *is* the "not installed" signal — so never create it as a side effect. The gate is self-contained: it never requires the skill-trust skill itself to be loadable, so a distributed skill degrades to a silent no-op for anyone without the framework.

## 0b. Opened event (enables abandonment tracking)

At skill entry, right after the install gate, run `trust-log.py SKILL opened` (helper below) and keep the printed `run_id`. Pass the same `run_id` to the terminal event. `opened` is unscored; a run with no terminal event after 24h is counted as abandoned by the scorer.

## 1. Event logging (after each user prompt interaction)

```
After each user prompt where the user accepts, modifies, or rejects a suggestion, append one line to `~/.claude/skill-trust/events.jsonl`:

{"ts": "{ISO-8601-now}", "skill": "{this-skill-name}", "version": "{version from trust-manifest.json}", "outcome": "{accepted|modified|rejected|cancelled}", "context": {relevant metadata}}

Log with the bundled helper, never hand-built JSON (it parses the manifest for `version`, validates the line, and is a no-op when the framework is absent):

  ~/.claude/skills/skill-trust/scripts/trust-log.py SKILL opened            # prints a new run_id
  ~/.claude/skills/skill-trust/scripts/trust-log.py SKILL OUTCOME RUN_ID ['{"repo":"x"}']   # terminal event; optional context JSON

Determine outcome by:
- User accepted with no changes → "accepted"
- User edited the suggestion before confirming → "modified"
- User said no, skipped, or chose differently → "rejected"
- User cancelled/exited the skill before completion → "cancelled"

Create `events.jsonl` if it's missing *inside the already-present* `~/.claude/skill-trust/` directory — but never create the directory itself (per the install gate). Always append, never overwrite.
```

## 1b. Explicit-question pattern (when the skill asks the user)

If your skill needs to actively ask the user how the result looked (e.g., audit/review skills where the outcome isn't inferred from a yes/no/edit choice), use the **`AskUserQuestion` tool** so the user can arrow-select or press the number directly. (This supersedes the older plain-text numbered-list format.)

Standard template — call `AskUserQuestion` with:

```
- question: "How did this {result type} look?"
- header: "{short label, e.g. 'Audit quality'}"
- multiSelect: false
- options (in this exact order):
  1. label: `Accurate`        — description: "{what counts as accurate}"
  2. label: `Mostly accurate` — description: "{description}"
  3. label: `Off-base`        — description: "{description}"

Map the selection to outcome: Accurate → accepted, Mostly accurate → modified,
Off-base → rejected. The auto-provided "Other" option (or no selection) → cancelled.
```

(Skills whose outcome is already implied by an action picker — accept/modify/skip — don't need this separate question; they derive the outcome from that choice.)

## 2. End-of-run trust summary

```
After all prompts are complete, read `~/.claude/skills/{this-skill}/trust-manifest.json` and compute the trust summary. Display:

Trust: {rolling_score}% (last {window}) | {alltime_score}% (all-time, n={total})
Threshold: {threshold}% — {READY|NOT YET|NEW (insufficient data)}
This run: {accepted} accepted, {modified} modified, {rejected} rejected, {cancelled} skipped

"READY" if rolling score >= threshold AND n >= rolling_window.
"NOT YET" if rolling score < threshold.
"NEW" if total events < rolling_window (insufficient data to judge).

Then check export prompt conditions (see "Export prompting" section in SKILL.md).
```
