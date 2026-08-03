# URN: test:author-plan-substrate:author-plan-spine:C008-SMOKE-001-plan-unit-spec-cli
# Acceptance: acc:author-plan-substrate:C008-SMOKE-001-seed
# WMBT: wmbt:author-plan-substrate:C008
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""C008-SMOKE-001 — the real `atdd plan unit --spec` CLI, driven as a subprocess.

Run-or-fail, no skip (#1298 live-smoke honesty): each test shells out to the
actual CLI under a temporary root and asserts the process exit code and what
landed on disk. The unit acceptances exercise the guard in-process; this one
proves the operator-facing surface — exit status and stderr — really behaves.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[4]
_SPEC = {"wagon": "play-audio", "description": "play audio during the commute smoke"}


def _sess(root: Path, *args: str) -> subprocess.CompletedProcess:
    env = {"PYTHONPATH": str(_SRC), "PATH": os.environ.get("PATH", ""), "HOME": str(root)}
    return subprocess.run([sys.executable, "-m", "atdd", "plan", "--root", str(root), *args],
                          cwd=str(root), env=env, capture_output=True, text=True, timeout=60)


def _to_prepare(root: Path, sid: str) -> None:
    (root / "plan").mkdir(exist_ok=True)
    assert _sess(root, "start", "--id", sid, "--main-job", "job", "--issue", "iss").returncode == 0
    assert _sess(root, "advance", "--id", sid, "--step", "attach").returncode == 0
    assert _sess(root, "source", "--id", sid, "a source").returncode == 0
    assert _sess(root, "advance", "--id", sid, "--step", "compose").returncode == 0


def _units(root: Path, sid: str) -> list:
    session = root / ".atdd" / "runtime" / "plan-sessions" / sid / "session.json"
    return json.loads(session.read_text())["units"]


def test_smoke_non_object_spec_is_refused_and_persists_nothing(tmp_path):
    _to_prepare(tmp_path, "sm1")

    r = _sess(tmp_path, "unit", "--id", "sm1", "--kind", "wagon", "--ref", "wagon:x", "--spec", "5")

    assert r.returncode != 0, f"a non-object spec must be refused; got exit 0\n{r.stdout}"
    assert _units(tmp_path, "sm1") == [], "a refused unit must never reach session.json"


def test_smoke_bare_path_is_refused_naming_spec_and_the_at_form(tmp_path):
    _to_prepare(tmp_path, "sm2")
    spec_file = tmp_path / "spec.json"
    spec_file.write_text(json.dumps(_SPEC))

    r = _sess(tmp_path, "unit", "--id", "sm2", "--kind", "wagon", "--ref", "wagon:x",
              "--spec", str(spec_file))

    assert r.returncode != 0, "a bare filesystem path must be refused"
    assert "--spec" in r.stderr, f"the refusal must name --spec; stderr was:\n{r.stderr}"
    assert "@" in r.stderr, f"the refusal must hint the @<path> form; stderr was:\n{r.stderr}"
    assert "Traceback" not in r.stderr, f"a traceback leaked to stderr:\n{r.stderr}"
    assert _units(tmp_path, "sm2") == []


def test_smoke_at_file_form_loads_the_object_spec(tmp_path):
    _to_prepare(tmp_path, "sm3")
    spec_file = tmp_path / "spec.json"
    spec_file.write_text(json.dumps(_SPEC))

    r = _sess(tmp_path, "unit", "--id", "sm3", "--kind", "wagon", "--ref", "wagon:x",
              "--spec", f"@{spec_file}")

    assert r.returncode == 0, f"--spec @<path> must be admitted; stderr:\n{r.stderr}"
    units = _units(tmp_path, "sm3")
    assert len(units) == 1 and units[0]["spec"] == _SPEC, "the file's object spec must persist"
