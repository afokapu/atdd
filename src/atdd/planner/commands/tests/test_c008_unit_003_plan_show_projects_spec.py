# URN: test:author-plan-substrate:author-plan-spine:C008-UNIT-003-plan-show-projects-the-unit-spec
# Acceptance: acc:author-plan-substrate:C008-UNIT-003-plan-show-projects-the-unit-spec
# WMBT: wmbt:author-plan-substrate:C008
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""C008-UNIT-003 (plan spine) — `atdd plan show` projects each unit's `spec`.

``spec`` is what a unit carries into the ``atdd author`` writers, so an operator
who cannot see it cannot tell what they attached without reading
``session.json`` by hand — which defeats the point of a ``show`` op.

RED: ``plan_session_cli._state()`` projected kind/ref/verdict/modification and
dropped ``spec``, so every unit rendered as
``{"kind":"wagon","modification":null,"ref":"w1","verdict":"pending"}``.

Refs #1235.
"""
from __future__ import annotations

import json
from pathlib import Path

from atdd.planner.commands.plan_session_cli import run

_SPEC = {"wagon": "play-audio", "description": "play audio on the commute"}


def _to_prepare(root: Path, sid: str) -> None:
    assert run(["--root", str(root), "start", "--id", sid, "--main-job", "job", "--issue", "iss"]) == 0
    assert run(["--root", str(root), "advance", "--id", sid, "--step", "locate"]) == 0
    assert run(["--root", str(root), "source", "--id", sid, "a source"]) == 0
    assert run(["--root", str(root), "advance", "--id", sid, "--step", "prepare"]) == 0


def test_show_projects_the_spec_each_unit_carries(tmp_path, capsys):
    _to_prepare(tmp_path, "s1")
    assert run(["--root", str(tmp_path), "unit", "--id", "s1", "--kind", "wagon",
                "--ref", "w1", "--spec", json.dumps(_SPEC)]) == 0
    capsys.readouterr()

    assert run(["--root", str(tmp_path), "show", "--id", "s1"]) == 0
    unit = json.loads(capsys.readouterr().out)["units"][0]
    assert unit["spec"] == _SPEC, (
        "show must render spec — it is what the unit carries into atdd author")


def test_show_keeps_projecting_the_existing_unit_fields(tmp_path, capsys):
    """Adding spec must not displace what show already rendered."""
    _to_prepare(tmp_path, "s2")
    assert run(["--root", str(tmp_path), "unit", "--id", "s2", "--kind", "wagon",
                "--ref", "w1", "--spec", json.dumps(_SPEC)]) == 0
    capsys.readouterr()

    assert run(["--root", str(tmp_path), "show", "--id", "s2"]) == 0
    unit = json.loads(capsys.readouterr().out)["units"][0]
    for key in ("kind", "ref", "verdict", "modification"):
        assert key in unit, f"show must keep projecting {key}"


def test_a_unit_with_no_spec_renders_an_empty_object(tmp_path, capsys):
    _to_prepare(tmp_path, "s3")
    assert run(["--root", str(tmp_path), "unit", "--id", "s3",
                "--kind", "wagon", "--ref", "w1"]) == 0
    capsys.readouterr()

    assert run(["--root", str(tmp_path), "show", "--id", "s3"]) == 0
    assert json.loads(capsys.readouterr().out)["units"][0]["spec"] == {}
