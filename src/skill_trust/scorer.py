"""Score a skill's event log against its manifest.

Pure functions plus a small CLI. The score is the Wilson lower bound of the
weighted mean, so a perfect score on a tiny sample is not flattering.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

Z95 = 1.96
ABANDON_AFTER = timedelta(hours=24)
TERMINAL = {"accepted", "modified", "rejected", "cancelled", "timeout"}


@dataclass
class Report:
    skill: str
    n: int
    mean: float | None
    lower: float | None
    rolling_lower: float | None
    abandoned: int
    runs: int
    malformed: int
    status: str
    by_version: dict[str, tuple[int, float]]


def normalize_version(v: object) -> str:
    """Collapse 'v1', '1.0', '1.0.0' to one spelling; anything odd is 'unknown'."""
    m = re.fullmatch(r"v?(\d+)(?:\.(\d+))?(?:\.(\d+))?", str(v or "").strip())
    if not m:
        return "unknown"
    return ".".join(g or "0" for g in m.groups())


def wilson_lower(successes: float, n: int, z: float = Z95) -> float:
    """Lower bound of the Wilson score interval; 0.0 when there is no data."""
    if n == 0:
        return 0.0
    p = successes / n
    denom = 1 + z * z / n
    centre = p + z * z / (2 * n)
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return max(0.0, (centre - margin) / denom)


def parse_ts(ts: str) -> datetime:
    return datetime.fromisoformat(ts)


def load_events(path: Path) -> tuple[list[dict], int]:
    """Read JSONL, skipping (and counting) lines that are not valid events."""
    events, bad = [], 0
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            e = json.loads(line)
            parse_ts(e["ts"])
            e["skill"], e["outcome"]
        except (ValueError, KeyError, TypeError):
            bad += 1
            continue
        events.append(e)
    return events, bad


def reconcile(events: list[dict], now: datetime) -> tuple[list[dict], int, int]:
    """Split events into scorable terminals and an abandoned-run count.

    A run is an 'opened' event with a run_id. If no terminal event shares its
    run_id within ABANDON_AFTER, the run was abandoned: the failure that a
    log written only at the end of a run can never record.
    """
    terminals = [e for e in events if e["outcome"] in TERMINAL]
    closed = {e["run_id"] for e in terminals if e.get("run_id")}
    opened = [e for e in events if e["outcome"] == "opened" and e.get("run_id")]
    abandoned = sum(
        1 for e in opened if e["run_id"] not in closed and now - parse_ts(e["ts"]) > ABANDON_AFTER
    )
    return terminals, abandoned, len(opened)


def score(
    events: list[dict], manifest: dict, now: datetime | None = None, malformed: int = 0
) -> Report:
    now = now or datetime.now(UTC)
    rules = manifest["individual_trust_rules"]
    weights, window, threshold = (
        rules["outcome_weights"],
        rules["rolling_window"],
        rules["threshold"],
    )
    skill = manifest["skill"]
    mine = [e for e in events if e["skill"] == skill]
    terminals, abandoned, runs = reconcile(mine, now)
    scored = sorted(
        (
            (parse_ts(e["ts"]), weights[e["outcome"]], normalize_version(e.get("version")))
            for e in terminals
            if weights.get(e["outcome"]) is not None
        ),
        key=lambda t: t[0],
    )
    values = [w for _, w, _ in scored]
    versions: dict[str, list[float]] = {}
    for _, w, v in scored:
        versions.setdefault(v, []).append(w)
    by_version = {v: (len(ws), sum(ws) / len(ws)) for v, ws in sorted(versions.items())}
    n = len(values)
    recent = values[-window:]
    lower = wilson_lower(sum(values), n) if n else None
    rolling_lower = wilson_lower(sum(recent), len(recent)) if recent else None
    if wilson_lower(window, window) < threshold:
        status = "UNREACHABLE"  # even a perfect window can't clear the gate
    elif n < window:
        status = "NEW"
    elif rolling_lower >= threshold:
        status = "READY"
    else:
        status = "NOT YET"
    return Report(
        skill,
        n,
        sum(values) / n if n else None,
        lower,
        rolling_lower,
        abandoned,
        runs,
        malformed,
        status,
        by_version,
    )


def format_report(r: Report) -> str:
    pct = lambda x: "n/a" if x is None else f"{x:.1%}"
    rate = f"{r.abandoned / r.runs:.0%} ({r.abandoned}/{r.runs})" if r.runs else "n/a"
    versions = "  ".join(f"{v}: {m:.0%} (n={c})" for v, (c, m) in r.by_version.items())
    return (
        f"{r.skill}: {r.status}\n"
        f"  n={r.n}  mean={pct(r.mean)}  wilson-lower={pct(r.lower)}  "
        f"rolling-lower={pct(r.rolling_lower)}\n"
        f"  abandoned runs: {rate}  malformed lines: {r.malformed}\n"
        f"  by version: {versions or 'n/a'}"
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="skill-trust", description=__doc__.splitlines()[0])
    ap.add_argument("manifest", type=Path, help="trust-manifest.json")
    ap.add_argument("events", type=Path, help="events.jsonl")
    args = ap.parse_args(argv)
    events, bad = load_events(args.events)
    print(format_report(score(events, json.loads(args.manifest.read_text()), malformed=bad)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
