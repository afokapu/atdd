# URN: test:govern-lifecycle:scoped-registry-gate-compares-the-whole-entry:E079-UNIT-001-the-scoped-gate-sees-every-field
# Acceptance: acc:govern-lifecycle:E079-UNIT-001-the-scoped-gate-sees-every-field
# WMBT: wmbt:govern-lifecycle:E079
# Phase: GREEN
# Layer: backend.unit
"""E079-UNIT-001 — the PR-scoped registry gate compares the whole entry (#1891).

`_drifted_wagon_slug` compared exactly ONE field, `description`, out of the
fourteen a wagon entry carries. So the gate could only ever catch two things: a
wagon absent from the aggregate, or a reworded description. Every other drift
passed — `wmbt`, `produce`, `consume`, `theme`, `subject`, `goal`, `outcome`,
`action`, `context`, `total`, `manifest`, `path`.

Measured on one commit: the full check said "Drift detected in wagon registry"
and the scoped gate said "1 wagon source(s) checked, all in sync". Same commit,
same file, opposite verdicts.

It now compares the entry `_build_wagon_entry` WOULD produce against the one
stored — the same builder the full check regenerates from. A scoped check that
re-implements the comparison drifts from the full one; a scoped check that reuses
the builder cannot.
"""
from __future__ import annotations

import pathlib

import pytest
import yaml

from atdd.coach.commands.registry import RegistryBuilder

SOURCE = "plan/demo_wagon/_demo_wagon.yaml"

_MANIFEST = {
    "wagon": "demo-wagon",
    "description": "A demo wagon.",
    "theme": "commons",
    "subject": "agent:operator",
    "context": "ctx",
    "action": "act",
    "goal": "goal",
    "outcome": "out",
    "produce": [{"name": "commons:demo:thing"}],
    "consume": [],
    "wmbt": {"total": 1, "C001": "minimize likelihood of x"},
    "total": 1,
}


@pytest.fixture()
def repo(tmp_path: pathlib.Path) -> pathlib.Path:
    (tmp_path / "plan" / "demo_wagon").mkdir(parents=True)
    (tmp_path / SOURCE).write_text(yaml.safe_dump(_MANIFEST, sort_keys=False), encoding="utf-8")
    builder = RegistryBuilder(tmp_path)
    entry = builder._build_wagon_entry(tmp_path / SOURCE)
    (tmp_path / "plan" / "_wagons.yaml").write_text(
        yaml.safe_dump({"wagons": [entry]}, sort_keys=False), encoding="utf-8"
    )
    return tmp_path


def _drifted(repo: pathlib.Path) -> bool:
    return RegistryBuilder(repo).check_wagon_registry_scoped([SOURCE])["has_changes"]


def _edit(repo: pathlib.Path, **changes) -> None:
    doc = yaml.safe_load((repo / SOURCE).read_text())
    doc.update(changes)
    (repo / SOURCE).write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")


def test_an_untouched_manifest_is_in_sync(repo) -> None:
    """The gate must not simply always fail."""
    assert _drifted(repo) is False


def test_a_reworded_description_is_drift(repo) -> None:
    """The one field the old gate did compare — still caught."""
    _edit(repo, description="Reworded.")
    assert _drifted(repo) is True


@pytest.mark.parametrize("field,value", [
    ("wmbt", {"total": 2, "C001": "minimize likelihood of x", "C002": "added"}),
    ("produce", [{"name": "commons:demo:thing"}, {"name": "commons:demo:other"}]),
    ("consume", [{"name": "commons:other:thing"}]),
    ("theme", "plan"),
    ("subject", "agent:planner"),
    ("goal", "a different goal"),
    ("outcome", "a different outcome"),
    ("action", "a different action"),
    ("context", "a different context"),
    ("total", 2),
])
def test_every_other_field_is_drift_too(repo, field: str, value) -> None:
    """THE DEFECT. Each of these changed the wagon and passed the old gate."""
    _edit(repo, **{field: value})
    assert _drifted(repo) is True, (
        f"a change to {field!r} is invisible to the scoped gate — it is comparing "
        "a subset of the entry again"
    )


def test_a_wagon_missing_from_the_aggregate_is_drift(repo) -> None:
    (repo / "plan" / "_wagons.yaml").write_text(
        yaml.safe_dump({"wagons": []}, sort_keys=False), encoding="utf-8"
    )
    assert _drifted(repo) is True


def test_an_unreadable_manifest_is_reported_not_swallowed(repo) -> None:
    """Nothing was established about whether it drifted, so the operator is made
    to look — the old code logged at debug and returned None, which reads as
    clean."""
    (repo / SOURCE).write_text("{{ not: valid: yaml", encoding="utf-8")
    assert _drifted(repo) is True


def test_a_pr_touching_no_wagon_source_is_a_trivial_pass(repo) -> None:
    """The scope is the point of the scoped gate; unrelated PRs stay fast."""
    result = RegistryBuilder(repo).check_wagon_registry_scoped(["src/atdd/cli.py"])
    assert result["has_changes"] is False
