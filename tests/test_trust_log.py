import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).parent.parent / "skill" / "scripts" / "trust-log.py"


def run(home, *args, extra_env=None):
    env = {"HOME": str(home), "PATH": ""}
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        env=env,
        capture_output=True,
        text=True,
        check=False,
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


def test_skill_trust_home_override_logs_to_alternate_root(tmp_path):
    root = tmp_path / "alt-root"
    (root / "skill-trust").mkdir(parents=True)
    skill = root / "skills" / "demo"
    skill.mkdir(parents=True)
    (skill / "trust-manifest.json").write_text(json.dumps({"version": "2.0.0"}))
    r = run(tmp_path, "demo", "accepted", "1", extra_env={"SKILL_TRUST_HOME": str(root)})
    assert r.returncode == 0
    lines = (root / "skill-trust" / "events.jsonl").read_text().splitlines()
    assert json.loads(lines[0])["version"] == "2.0.0"
    assert not (tmp_path / ".claude" / "skill-trust").exists()


def test_skill_trust_home_override_absent_is_noop(tmp_path):
    setup(tmp_path)
    r = run(tmp_path, "demo", "opened", extra_env={"SKILL_TRUST_HOME": str(tmp_path / "elsewhere")})
    assert r.returncode == 0 and r.stdout == ""
