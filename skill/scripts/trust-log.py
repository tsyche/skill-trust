#!/usr/bin/env python3
"""Append one skill-trust event. Usage: trust-log.py SKILL OUTCOME [RUN_ID] [CONTEXT_JSON]
OUTCOME 'opened' with no RUN_ID generates one and prints it. No-op if skill-trust
is absent under SKILL_TRUST_HOME (default ~/.claude)."""

import datetime
import json
import os
import sys
import time

skill, outcome = sys.argv[1], sys.argv[2]
run_id = sys.argv[3] if len(sys.argv) > 3 else None
context = json.loads(sys.argv[4]) if len(sys.argv) > 4 else {}
root = os.path.expanduser(os.environ.get("SKILL_TRUST_HOME", "~/.claude"))
if not os.path.isdir(f"{root}/skill-trust"):
    sys.exit(0)
if outcome == "opened" and not run_id:
    run_id = str(time.time_ns())
    print(run_id)
try:
    with open(f"{root}/skills/{skill}/trust-manifest.json") as f:
        manifest = json.load(f)
except (OSError, ValueError) as err:
    print(f"trust-log: no usable manifest for {skill} ({err}); event not logged", file=sys.stderr)
    sys.exit(0)
event = {
    "ts": datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "skill": skill,
    "version": str(manifest["version"]),
    "outcome": outcome,
}
if run_id:
    event["run_id"] = run_id
if context:
    event["context"] = context
line = json.dumps(event)
json.loads(line)
with open(f"{root}/skill-trust/events.jsonl", "a") as f:
    f.write(line + "\n")
