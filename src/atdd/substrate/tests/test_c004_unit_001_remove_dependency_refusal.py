# URN: test:admit-substrate:substrate-admission:C004-UNIT-001-remove-dependency-refusal
# Acceptance: acc:admit-substrate:C004-UNIT-001-remove-dependency-refusal
# WMBT: wmbt:admit-substrate:C004
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""C004-UNIT-001 — removing a depended-on artifact is refused; --force overrides; a
leaf removes cleanly leaving its shared workspace; --prune drops a now-unused workspace."""
from __future__ import annotations

import pytest

from atdd.substrate import admission, installer

WS = {
    "id": "acme.workspace.ws",
    "kind": "workspace",
    "version": "1.0.0",
    "digest": "sha256:" + "a" * 64,
    "installed_path": ".atdd/workspaces/acme.workspace.ws/1.0.0",
}
DEP = {
    "id": "acme.extension.dep",
    "kind": "extension",
    "version": "0.1.0",
    "digest": "sha256:" + "b" * 64,
    "installed_path": ".atdd/extensions/acme.extension.dep/0.1.0",
    "workspaces": [{"id": "acme.workspace.ws"}],
}
LEAF = {
    "id": "acme.extension.leaf",
    "kind": "extension",
    "version": "0.1.0",
    "digest": "sha256:" + "c" * 64,
    "installed_path": ".atdd/extensions/acme.extension.leaf/0.1.0",
}


def _seed(tmp_path) -> None:
    for entry in (WS, DEP, LEAF):
        installer.upsert_lock_entry(tmp_path, dict(entry))


def _ids(tmp_path) -> set:
    return {a["id"] for a in installer.list_substrate(tmp_path)}


def test_remove_depended_on_refused(tmp_path) -> None:
    _seed(tmp_path)
    with pytest.raises(admission.AdmissionError) as exc:
        admission.remove("acme.workspace.ws", project_root=tmp_path)
    assert "acme.extension.dep" in str(exc.value)
    assert "acme.workspace.ws" in _ids(tmp_path)  # unchanged


def test_force_removes_depended_on(tmp_path) -> None:
    _seed(tmp_path)
    admission.remove("acme.workspace.ws", project_root=tmp_path, force=True)
    assert "acme.workspace.ws" not in _ids(tmp_path)


def test_leaf_removes_and_keeps_shared_workspace(tmp_path) -> None:
    _seed(tmp_path)
    admission.remove("acme.extension.leaf", project_root=tmp_path)
    ids = _ids(tmp_path)
    assert "acme.extension.leaf" not in ids
    assert "acme.workspace.ws" in ids  # still needed by dep


def test_prune_removes_now_unused_workspace(tmp_path) -> None:
    _seed(tmp_path)
    out = admission.remove("acme.extension.dep", project_root=tmp_path, prune=True)
    ids = _ids(tmp_path)
    assert "acme.extension.dep" not in ids
    assert "acme.workspace.ws" not in ids  # pruned (no remaining dependent)
    assert "acme.workspace.ws" in out["pruned"]
