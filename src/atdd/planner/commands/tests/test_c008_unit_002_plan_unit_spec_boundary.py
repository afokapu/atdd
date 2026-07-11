# URN: test:author-plan-substrate:author-plan-spine:C008-UNIT-002-plan-unit-spec-boundary-refuses-and-reads-at-file
# Acceptance: acc:author-plan-substrate:C008-UNIT-002-plan-unit-spec-boundary-refuses-and-reads-at-file
# WMBT: wmbt:author-plan-substrate:C008
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""C008-UNIT-002 (plan spine) — the `atdd plan unit --spec` boundary.

`--spec` accepts an inline JSON object, or an explicit ``@<path>`` file form.
Everything else is refused with exit 2 and a message naming ``--spec`` — never
a traceback, and never a silent exit 0 that persists a corrupt unit.

A bare filesystem path is refused with a hint naming the ``@`` form rather than
autodetected: path autodetection would make the meaning of ``--spec`` depend on
filesystem state, so the same command would behave differently on two machines.

RED: `atdd plan unit --spec` calls json.loads() bare — a non-object spec exits 0
and persists, an unparseable spec raises JSONDecodeError and exits 1.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from atdd.planner.commands.plan_session_cli import run

_SPEC = {"wagon": "play-audio", "description": "play audio on the commute"}


def _to_prepare(root: Path, sid: str) -> None:
    assert run(["--root", str(root), "start", "--id", sid, "--main-job", "job", "--issue", "iss"]) == 0
    assert run(["--root", str(root), "advance", "--id", sid, "--step", "locate"]) == 0
    assert run(["--root", str(root), "source", "--id", sid, "a source"]) == 0
    assert run(["--root", str(root), "advance", "--id", sid, "--step", "prepare"]) == 0


def _unit(root: Path, sid: str, spec_arg: str) -> int:
    return run(["--root", str(root), "unit", "--id", sid, "--kind", "wagon",
                "--ref", "wagon:play-audio", "--spec", spec_arg])


def _units(root: Path, sid: str) -> list:
    state = json.loads((root / ".atdd" / "runtime" / "plan-sessions" / sid / "session.json").read_text())
    return state["units"]


def test_inline_json_object_is_admitted(tmp_path):
    _to_prepare(tmp_path, "s1")
    assert _unit(tmp_path, "s1", json.dumps(_SPEC)) == 0
    units = _units(tmp_path, "s1")
    assert len(units) == 1 and units[0]["spec"] == _SPEC


def test_at_file_form_reads_the_object_from_disk(tmp_path):
    _to_prepare(tmp_path, "s2")
    spec_file = tmp_path / "spec.json"
    spec_file.write_text(json.dumps(_SPEC))

    assert _unit(tmp_path, "s2", f"@{spec_file}") == 0
    units = _units(tmp_path, "s2")
    assert len(units) == 1 and units[0]["spec"] == _SPEC, "@<path> must load the object from the file"


def test_unparseable_spec_exits_two_naming_the_flag(tmp_path, capsys):
    _to_prepare(tmp_path, "s3")
    assert _unit(tmp_path, "s3", "{not-valid-json") == 2
    err = capsys.readouterr().err
    assert "--spec" in err, "the refusal must name the offending argument"
    assert "Traceback" not in err
    assert _units(tmp_path, "s3") == [], "a refused unit must not be persisted"


@pytest.mark.parametrize("spec_arg", ['"hello"', "[1,2]", "5", "null", "true"])
def test_non_object_json_exits_two_and_persists_nothing(tmp_path, spec_arg):
    sid = "s4" + spec_arg.strip('"[]')[:2].replace(",", "").replace("-", "")
    _to_prepare(tmp_path, sid)
    assert _unit(tmp_path, sid, spec_arg) == 2, f"{spec_arg} is valid JSON but not an object"
    assert _units(tmp_path, sid) == [], "a non-object spec must never reach the session"


def test_bare_path_is_refused_with_an_at_hint(tmp_path, capsys):
    _to_prepare(tmp_path, "s5")
    spec_file = tmp_path / "spec.json"
    spec_file.write_text(json.dumps(_SPEC))

    assert _unit(tmp_path, "s5", str(spec_file)) == 2
    err = capsys.readouterr().err
    assert "--spec" in err
    assert "@" in err, "a bare path must be refused with a hint naming the @<path> form"
    assert _units(tmp_path, "s5") == []
