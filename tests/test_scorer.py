import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from skill_trust.scorer import load_events, main, normalize_version, score, wilson_lower

NOW = datetime(2026, 2, 1, tzinfo=UTC)
EXAMPLES = Path(__file__).parent.parent / "examples"


def manifest(window=10, threshold=0.75):
    return {
        "skill": "s",
        "individual_trust_rules": {
            "threshold": threshold,
            "rolling_window": window,
            "outcome_weights": {
                "accepted": 1.0,
                "modified": 0.5,
                "rejected": 0.0,
                "cancelled": None,
                "timeout": None,
            },
        },
    }


def ev(day, outcome, run_id=None, skill="s"):
    e = {"ts": f"2026-01-{day:02d}T00:00:00Z", "skill": skill, "outcome": outcome}
    if run_id:
        e["run_id"] = run_id
    return e


@pytest.mark.parametrize("n,successes,expected", [(10, 9, 0.596), (20, 18, 0.699), (30, 27, 0.744)])
def test_wilson_matches_published_values(n, successes, expected):
    assert wilson_lower(successes, n) == pytest.approx(expected, abs=1e-3)


def test_wilson_no_data_is_zero():
    assert wilson_lower(0, 0) == 0.0


def test_perfect_small_sample_is_never_ready():
    events = [ev(d, "accepted") for d in range(1, 7)]
    r = score(events, manifest(window=6, threshold=0.75), NOW)
    assert r.mean == 1.0
    assert r.lower < 0.75  # 6/6 still fails the lower-bound gate
    assert r.status != "READY"


def test_gate_a_perfect_window_cannot_clear_is_unreachable():
    events = [ev(d, "accepted") for d in range(1, 25)]
    # 20/20 perfect scores a Wilson lower bound of ~0.839, so 0.90 can never pass
    assert score(events, manifest(window=20, threshold=0.90), NOW).status == "UNREACHABLE"


def test_insufficient_data_is_new_not_ready():
    r = score([ev(1, "accepted")], manifest(window=10, threshold=0.5), NOW)
    assert r.status == "NEW"


def test_ready_needs_lower_bound_over_threshold():
    events = [ev(d, "accepted") for d in range(1, 29)]
    assert score(events, manifest(window=20, threshold=0.80), NOW).status == "READY"


def test_null_weight_outcomes_excluded_from_score():
    events = [ev(1, "accepted"), ev(2, "cancelled"), ev(3, "timeout")]
    assert score(events, manifest(), NOW).n == 1


def test_opened_without_terminal_is_abandoned():
    events = [ev(1, "opened", "a"), ev(1, "opened", "b"), ev(1, "accepted", "b")]
    r = score(events, manifest(), NOW)
    assert (r.abandoned, r.runs, r.n) == (1, 2, 1)  # abandoned is tracked, not scored


def test_recent_open_run_is_not_yet_abandoned():
    events = [{"ts": "2026-01-31T23:00:00Z", "skill": "s", "outcome": "opened", "run_id": "a"}]
    assert score(events, manifest(), NOW).abandoned == 0


def test_version_spellings_score_together():
    events = [
        {**ev(1, "accepted"), "version": "1.0"},
        {**ev(2, "accepted"), "version": "1.0.0"},
        {**ev(3, "rejected"), "version": "v2"},
    ]
    assert score(events, manifest(), NOW).by_version == {"1.0.0": (2, 1.0), "2.0.0": (1, 0.0)}


def test_other_skills_ignored():
    events = [ev(1, "accepted"), ev(2, "rejected", skill="other")]
    assert score(events, manifest(), NOW).n == 1


@pytest.mark.parametrize(
    "raw,norm",
    [
        ("v1", "1.0.0"),
        ("1.0", "1.0.0"),
        ("1.0.0", "1.0.0"),
        ("unknown", "unknown"),
        ("", "unknown"),
        (None, "unknown"),
    ],
)
def test_version_spellings_collapse(raw, norm):
    assert normalize_version(raw) == norm


def test_malformed_lines_are_counted_not_fatal(tmp_path):
    f = tmp_path / "e.jsonl"
    f.write_text(json.dumps(ev(1, "accepted")) + '\nnot json\n{"ts": "bad"}\n\n')
    events, bad = load_events(f)
    assert (len(events), bad) == (1, 2)


def test_cli_on_example_data(capsys):
    assert main([str(EXAMPLES / "trust-manifest.json"), str(EXAMPLES / "events.sample.jsonl")]) == 0
    out = capsys.readouterr().out
    assert "demo-skill: NOT YET" in out
    assert "wilson-lower=60.1%" in out
    assert "demo-skill" in out and "abandoned runs: 22% (4/18)" in out
