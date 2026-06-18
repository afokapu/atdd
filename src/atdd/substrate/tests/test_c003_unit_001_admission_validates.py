# URN: test:admit-substrate:substrate-admission:C003-UNIT-001-admission-validates
# Acceptance: acc:admit-substrate:C003-UNIT-001-admission-validates
# WMBT: wmbt:admit-substrate:C003
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""C003-UNIT-001 — a well-formed package passes admission validation; a malformed
manifest, a missing owned file, and an invalid realizes mapping are each refused."""
from __future__ import annotations

import pathlib
import shutil

import pytest
import yaml

from atdd.planner.commands.author_manifest import AuthorInputError
from atdd.planner.commands.compose import CompositionError
from atdd.substrate import admission

VALID = pathlib.Path(__file__).parent / "fixtures" / "valid_extension"
_REFUSALS = (admission.AdmissionError, AuthorInputError, CompositionError, ValueError)


def _copy(tmp_path) -> pathlib.Path:
    dst = tmp_path / "pkg"
    shutil.copytree(VALID, dst)
    return dst


def _manifest(d: pathlib.Path) -> dict:
    return yaml.safe_load((d / "atdd.extension.yaml").read_text())


def _write(d: pathlib.Path, m: dict) -> None:
    (d / "atdd.extension.yaml").write_text(yaml.safe_dump(m, sort_keys=False))


def test_valid_package_passes(tmp_path) -> None:
    res = admission.validate_and_compose(_copy(tmp_path))
    assert res.kind == "extension"
    assert res.package_id == "acme.extension.demo"
    assert res.executed_implementations == []


def test_malformed_manifest_refused(tmp_path) -> None:
    d = _copy(tmp_path)
    m = _manifest(d)
    del m["extension_id"]
    _write(d, m)
    with pytest.raises(_REFUSALS):
        admission.validate_and_compose(d)


def test_missing_owned_file_refused(tmp_path) -> None:
    d = _copy(tmp_path)
    m = _manifest(d)
    m["owns"]["implementations"] = ["implementations/ghost"]
    _write(d, m)
    with pytest.raises(admission.AdmissionError):
        admission.validate_and_compose(d)


def test_invalid_realizes_refused(tmp_path) -> None:
    d = _copy(tmp_path)
    m = _manifest(d)
    m["realizes"] = [{"extension_node": "x.not.owned", "core_node": "coach.bogus.does-not-exist"}]
    _write(d, m)
    with pytest.raises(_REFUSALS):
        admission.validate_and_compose(d, core_ids={"coach.lifecycle.phase-machine"})
