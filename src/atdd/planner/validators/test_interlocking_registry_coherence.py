# URN: component:plan:train-interlocking:RegistryCoherence:backend:tests
# Runtime: python
# Purpose: Planner validator for registry/document field agreement (#1855).
"""The interlocking registry must agree with the documents it indexes (#1855).

``plan/_trains/_interlockings.yaml`` denormalises three fields out of each
document it points at — ``theme``, ``status`` and now ``surfaces``. Nothing
checked them. Measured before writing this: editing one entry to read
``theme: plan, status: checked`` while its document says ``theme: commons,
status: draft`` left 29 planner validators green.

That mattered little while the mirrored fields were descriptive. ``surfaces`` is
not descriptive — a consumer filters on it, so a registry that disagrees with its
document routes a document to the wrong stack, which is the failure #1818 was
filed about.

The document is AUTHORITATIVE and the registry is discovery metadata, so the
direction is fixed: on disagreement the registry is the defect, never the
document.

**Every emittable status has a fault-injection test.** A clean-baseline assertion
on a rule that cannot emit passes forever, so the clean case here is paired with
one fault per mirrored field, driven through on-disk repos under ``tmp_path``.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import pytest
import yaml

from atdd.coach.utils.repo import find_repo_root
from atdd.coach.utils.rule_binding import bind_rule

_RULE_ID = "planner.interlocking.registry-mirrors-document"
_RULE = bind_rule(_RULE_ID)
_NODES_DIR = "src/atdd/planner/conventions/nodes"

#: Fields the registry copies from the document. Adding one here is the only
#: change needed to police it — the check is driven by this tuple, not by a
#: hand-written comparison per field.
MIRRORED_FIELDS: tuple[str, ...] = ("theme", "status", "surfaces")

REGISTRY_REL = "plan/_trains/_interlockings.yaml"


def _document_value(doc: Dict[str, Any], field: str) -> Any:
    """Read a mirrored field from the document.

    ``surfaces`` lives under ``entrypoint``; the others are top level. Kept as a
    lookup rather than a getattr chain so a missing field reads as absent rather
    than raising — an absent field is a disagreement to report, not a crash.
    """
    if field == "surfaces":
        return (doc.get("entrypoint") or {}).get("surfaces")
    return doc.get(field)


def registry_violations(repo_root: Path) -> List[Dict[str, Any]]:
    """Every registry entry that disagrees with the document it points at."""
    registry_path = repo_root / REGISTRY_REL
    if not registry_path.is_file():
        return []
    registry = yaml.safe_load(registry_path.read_text()) or {}
    out: List[Dict[str, Any]] = []
    for entry in registry.get("interlockings") or []:
        if not isinstance(entry, dict):
            continue
        iid = entry.get("interlocking_id")
        rel = entry.get("path")
        if not iid or not rel:
            continue  # shape is the registry schema's business, not ours
        doc_path = repo_root / rel
        if not doc_path.is_file():
            out.append({
                "interlocking_id": iid,
                "field": "path",
                "registry_value": rel,
                "document_value": None,
            })
            continue
        doc = yaml.safe_load(doc_path.read_text()) or {}
        for field in MIRRORED_FIELDS:
            if field not in entry:
                continue  # the registry schema decides which are required
            registry_value = entry.get(field)
            document_value = _document_value(doc, field)
            if registry_value != document_value:
                out.append({
                    "interlocking_id": iid,
                    "field": field,
                    "registry_value": registry_value,
                    "document_value": document_value,
                })
    return out


def _materialize(tmp_path: Path, *, entry: Dict[str, Any], doc: Dict[str, Any]) -> Path:
    """A minimal on-disk repo: one registry entry and the document it indexes."""
    rel = "plan/_trains/_interlockings/probe.yaml"
    (tmp_path / "plan/_trains/_interlockings").mkdir(parents=True, exist_ok=True)
    (tmp_path / rel).write_text(yaml.safe_dump(doc, sort_keys=False))
    full_entry = {"interlocking_id": "interlocking:probe", "path": rel, **entry}
    (tmp_path / REGISTRY_REL).write_text(
        yaml.safe_dump({"version": "1.0", "interlockings": [full_entry]}, sort_keys=False)
    )
    return tmp_path


def _doc(**over: Any) -> Dict[str, Any]:
    base = {
        "interlocking_id": "interlocking:probe",
        "theme": "commons",
        "status": "draft",
        "entrypoint": {
            "exposed": False,
            "actions": [],
            "reason": "planned-not-exposed",
            "surfaces": ["backend"],
        },
    }
    base.update(over)
    return base


def test_live_registry_agrees_with_every_document_it_indexes():
    """The clean baseline — meaningful only because the faults below prove the
    rule can actually emit."""
    assert registry_violations(find_repo_root()) == []


@pytest.mark.parametrize(
    "field,registry_value,document_value",
    [
        ("theme", "plan", "commons"),
        ("status", "checked", "draft"),
        ("surfaces", ["frontend"], ["backend"]),
    ],
)
def test_a_registry_entry_that_disagrees_with_its_document_is_reported(
    tmp_path, field, registry_value, document_value
):
    """One fault per mirrored field.

    The ``surfaces`` case is the one with teeth: a registry claiming
    ``[frontend]`` over a ``[backend]`` document routes it to the Vite family,
    which is the misclassification #1818 measured at 23 false positives.
    """
    entry = {"theme": "commons", "status": "draft", "surfaces": ["backend"]}
    entry[field] = registry_value
    root = _materialize(tmp_path, entry=entry, doc=_doc())
    violations = registry_violations(root)
    assert len(violations) == 1, violations
    v = violations[0]
    assert v["field"] == field
    assert v["registry_value"] == registry_value
    assert v["document_value"] == document_value


def test_every_emitted_evidence_key_is_declared_by_the_convention_node(tmp_path):
    """Evidence the node does not declare cannot be acted on by a consumer."""
    root = _materialize(
        tmp_path,
        entry={"theme": "plan", "status": "draft", "surfaces": ["backend"]},
        doc=_doc(),
    )
    node = find_repo_root() / _NODES_DIR / f"{_RULE_ID}.convention.yaml"
    doc = yaml.safe_load(node.read_text(encoding="utf-8"))
    declared = set((doc.get("validation") or {}).get("failure_evidence") or [])
    for v in registry_violations(root):
        assert set(v) <= declared, f"undeclared evidence keys: {set(v) - declared}"


def test_an_entry_pointing_at_a_missing_document_is_reported(tmp_path):
    """A dangling path is a disagreement too — the registry claims a document
    that is not there, which no consumer can resolve."""
    (tmp_path / "plan/_trains/_interlockings").mkdir(parents=True, exist_ok=True)
    (tmp_path / REGISTRY_REL).write_text(
        yaml.safe_dump(
            {"version": "1.0", "interlockings": [
                {"interlocking_id": "interlocking:gone",
                 "path": "plan/_trains/_interlockings/gone.yaml",
                 "surfaces": ["backend"]}
            ]},
            sort_keys=False,
        )
    )
    violations = registry_violations(tmp_path)
    assert [v["field"] for v in violations] == ["path"]


def test_the_document_is_authoritative_so_a_matching_pair_is_clean(tmp_path):
    root = _materialize(
        tmp_path,
        entry={"theme": "commons", "status": "draft", "surfaces": ["backend"]},
        doc=_doc(),
    )
    assert registry_violations(root) == []
