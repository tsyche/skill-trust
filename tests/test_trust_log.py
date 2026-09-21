import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).parent.parent / "skill" / "scripts" / "trust-log.py"


def run(home, *args):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        env={"HOME": str(home), "PATH": ""},
        capture_output=True,
        text=True,
    )


def setup(home, framework=True, manifest=True):
    if framework:
        (home / ".claude" / "skill-trust").mkdir(parents=True)
    if manifest:
        skill = home / ".claude" / "skills" / "demo"
        skill.mkdir(parents=True)
        (skill / "trust-manifest.json").write_text(json.dumps({"version": "1.0.0"}))


def events(home):
    return (home / ".claude" / "skill-trust" / "events.jsonl").read_text().splitlines()


def test_noop_when_framework_absent(tmp_path):
    setup(tmp_path, framework=False)
    r = run(tmp_path, "demo", "opened")
    assert r.returncode == 0 and r.stdout == ""
    assert not (tmp_path / ".claude" / "skill-trust").exists()


def test_opened_prints_run_id_and_terminal_reuses_it(tmp_path):
    setup(tmp_path)
    run_id = run(tmp_path, "demo", "opened").stdout.strip()
    assert run_id.isdigit()
    run(tmp_path, "demo", "accepted", run_id, '{"repo": "x"}')
    opened, done = (json.loads(line) for line in events(tmp_path))
    assert opened["outcome"] == "opened" and opened["run_id"] == run_id
    assert done["outcome"] == "accepted" and done["run_id"] == run_id
    assert done["context"] == {"repo": "x"} and done["version"] == "1.0.0"


def test_missing_manifest_does_not_fail_or_log(tmp_path):
    setup(tmp_path, manifest=False)
    r = run(tmp_path, "demo", "accepted", "1")
    assert r.returncode == 0 and "no usable manifest" in r.stderr
    assert not (tmp_path / ".claude" / "skill-trust" / "events.jsonl").exists()
