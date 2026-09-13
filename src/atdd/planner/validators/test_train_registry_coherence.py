# URN: component:plan:train-registry:RegistryCoherence:backend:tests
# Runtime: python
# Purpose: Planner validator for train registry/document existence coherence (#1942).
"""The train registry and the documents it indexes must both exist (#1942).

``planner.train.registry`` has claimed since it was authored — at
``disposition: strict`` — that "every registry entry MUST have a corresponding
spec file". Nothing checked it. Its ``implementation.ref`` pointed at
``conventions/resolution/test_train_validation::test_fault_injection_and_legacy_parity``,
which resolves train→wagon *references* and never reads a path; and because the
binding gate exempts convention-variant refs from the ``bind_rule`` requirement,
the dead binding drew no complaint. The rule that should have caught this defect
existed the whole time and had never been able to fire. This module is what makes
it real.

Measured before writing it, by injecting each residue into the real corpus and
diffing against the clean baseline of 449 passed:

* a registry row naming an absent document → **not reported**. Worse than
  unreported: ``test_route_space_admission`` dies on it with a bare
  ``FileNotFoundError`` at the line that reads ``entry["path"]``, so the gate
  stops diagnosing the defect and starts crashing on it.
* a per-train document that no registry row names → **not reported at all**
  (449 passed, unchanged). The train loaders walk registry rows, never the
  ``plan/_trains/**`` tree, so an orphan is perfectly invisible.

Both directions matter, and they are not symmetric in severity. A dangling row is
a pointer consumers resolve through; an orphan is inert but is the residue the
#1942 ordering fix deliberately chose to leave, so it must be findable or that
choice is unsupported.

The sibling artifacts already have this and are untouched here:
``planner.interlocking.registry-mirrors-document`` reports the dangling direction
for interlockings and ``planner.train.interlocking-home`` the orphan direction.

**Every emittable direction has a fault-injection test**, driven through on-disk
repos under ``tmp_path`` — a clean-baseline assertion on a rule that cannot emit
is exactly the failure this module exists to correct.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import pytest
import yaml

from atdd.coach.utils.repo import find_repo_root
from atdd.coach.utils.rule_binding import bind_rule

_RULE_ID = "planner.train.registry"
_RULE = bind_rule(_RULE_ID)
_NODES_DIR = "src/atdd/planner/conventions/nodes"

REGISTRY_REL = "plan/_trains.yaml"
TRAINS_DIR_REL = "plan/_trains"


def _registry_rows(repo_root: Path) -> List[Dict[str, Any]]:
    """Every train entry in the registry, flattened across theme/category buckets.

    A malformed registry is not this rule's business — ``planner.train.definition``
    and the author's own shape guard own that — so anything that is not a mapping
    of buckets of entry dicts is simply skipped rather than raised on.
    """
    registry_path = repo_root / REGISTRY_REL
    if not registry_path.is_file():
        return []
    registry = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}
    if not isinstance(registry, dict):
        return []
    trains = registry.get("trains")
    if not isinstance(trains, dict):
        return []
    rows: List[Dict[str, Any]] = []
    for buckets in trains.values():
        if not isinstance(buckets, dict):
            continue
        for entries in buckets.values():
            for entry in entries or []:
                if isinstance(entry, dict):
                    rows.append(entry)
    return rows


def _per_train_documents(repo_root: Path) -> List[str]:
    """Repo-relative paths of every per-train document under ``plan/_trains``.

    Underscore-prefixed names are registry sidecars and sibling homes, not trains:
    ``_trains.yaml`` itself, ``_aliases.yaml``, and the whole ``_interlockings/``
    subtree, which has its own coherence rules. The check is applied to every path
    segment, so a future ``_<whatever>/`` home is excluded by construction rather
    than by being added to a list here.
    """
    trains_dir = repo_root / TRAINS_DIR_REL
    if not trains_dir.is_dir():
        return []
    out: List[str] = []
    for path in sorted(trains_dir.rglob("*.yaml")):
        rel_parts = path.relative_to(trains_dir).parts
        if any(part.startswith("_") for part in rel_parts):
            continue
        out.append(path.relative_to(repo_root).as_posix())
    return out


def registry_violations(repo_root: Path) -> List[Dict[str, Any]]:
    """Every incoherence between the train registry and the documents on disk.

    Two directions, one evidence shape:

    * ``dangling`` — a registry row whose ``path`` is not a file. A pointer that
      every consumer resolves through and that crashes the ones that do.
    * ``orphan`` — a per-train document that no registry row names. Inert, but it
      is the residue the write ordering deliberately leaves, so it must be found.
    """
    out: List[Dict[str, Any]] = []
    rows = _registry_rows(repo_root)

    registered_paths = set()
    for entry in rows:
        train_id = entry.get("train_id")
        rel = entry.get("path")
        if not train_id or not rel:
            continue  # row shape is the registry schema's business, not ours
        registered_paths.add(rel)
        if not (repo_root / rel).is_file():
            out.append({
                "train_id": train_id,
                "direction": "dangling",
                "registry_value": rel,
                "document_value": None,
            })

    for rel in _per_train_documents(repo_root):
        if rel in registered_paths:
            continue
        try:
            doc = yaml.safe_load((repo_root / rel).read_text(encoding="utf-8")) or {}
        except Exception:
            doc = {}
        out.append({
            "train_id": (doc.get("train_id") if isinstance(doc, dict) else None),
            "direction": "orphan",
            "registry_value": None,
            "document_value": rel,
        })
    return out


# ---------------------------------------------------------------------------
# Live corpus gate
# ---------------------------------------------------------------------------
def test_every_registry_row_resolves_and_every_document_is_registered() -> None:
    """The clean baseline — meaningful only because the faults below prove the
    rule can actually emit. Measured at authoring time: 21 rows, 21 documents,
    zero violations either way, so this lands strict with no advisory ratchet."""
    assert registry_violations(find_repo_root()) == []


# ---------------------------------------------------------------------------
# Fault injection — one per emittable direction
# ---------------------------------------------------------------------------
def _materialize(tmp_path: Path, *, rows: List[Dict[str, Any]],
                 documents: Dict[str, Dict[str, Any]]) -> Path:
    """A minimal on-disk repo: a bucketed registry plus the documents it indexes."""
    (tmp_path / TRAINS_DIR_REL).mkdir(parents=True, exist_ok=True)
    (tmp_path / REGISTRY_REL).write_text(
        yaml.safe_dump({"trains": {"plan": {"nominal": rows}}}, sort_keys=False),
        encoding="utf-8",
    )
    for rel, doc in documents.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
    return tmp_path


def _row(train_id: str, rel: str) -> Dict[str, Any]:
    return {"train_id": train_id, "description": "probe", "path": rel,
            "wagons": [], "category": "nominal"}


def _doc(train_id: str) -> Dict[str, Any]:
    return {"train_id": train_id, "title": "probe", "description": "probe",
            "themes": ["plan"], "sequence": [], "participants": [],
            "status": "planned"}


_REL = "plan/_trains/probe-subject/probe.yaml"
_TID = "train:probe-subject:probe"


def test_a_registry_row_naming_an_absent_document_is_reported(tmp_path):
    """The #1942 residue: the row survived, the document write did not."""
    root = _materialize(tmp_path, rows=[_row(_TID, _REL)], documents={})

    violations = registry_violations(root)

    assert len(violations) == 1, violations
    v = violations[0]
    assert v["direction"] == "dangling"
    assert v["train_id"] == _TID
    assert v["registry_value"] == _REL
    assert v["document_value"] is None


def test_a_document_no_registry_row_names_is_reported(tmp_path):
    """The residue the corrected write ordering leaves instead — inert, but only
    because something finds it."""
    root = _materialize(tmp_path, rows=[], documents={_REL: _doc(_TID)})

    violations = registry_violations(root)

    assert len(violations) == 1, violations
    v = violations[0]
    assert v["direction"] == "orphan"
    assert v["train_id"] == _TID
    assert v["registry_value"] is None
    assert v["document_value"] == _REL


def test_a_matched_row_and_document_is_clean(tmp_path):
    root = _materialize(tmp_path, rows=[_row(_TID, _REL)], documents={_REL: _doc(_TID)})
    assert registry_violations(root) == []


def test_registry_sidecars_and_interlockings_are_not_mistaken_for_trains(tmp_path):
    """``_aliases.yaml`` and the ``_interlockings/`` subtree are not per-train
    documents; counting them would emit a permanent false orphan for every repo."""
    root = _materialize(tmp_path, rows=[], documents={})
    (root / "plan/_trains/_aliases.yaml").write_text("aliases: {}\n", encoding="utf-8")
    (root / "plan/_trains/_interlockings").mkdir(parents=True, exist_ok=True)
    (root / "plan/_trains/_interlockings/probe.yaml").write_text(
        "interlocking_id: interlocking:probe\n", encoding="utf-8")

    assert registry_violations(root) == []


def test_a_legacy_flat_train_document_is_covered_too(tmp_path):
    """Typed trains nest at ``<subject>/<slug>.yaml``; the legacy ``NNNN-slug``
    form is flat. Both are per-train documents and both must be policed."""
    rel = "plan/_trains/0009-legacy-probe.yaml"
    root = _materialize(tmp_path, rows=[], documents={rel: _doc("0009-legacy-probe")})

    violations = registry_violations(root)

    assert [v["direction"] for v in violations] == ["orphan"]
    assert violations[0]["document_value"] == rel


def test_both_directions_are_reported_together(tmp_path):
    """A registry and a tree that disagree in both directions at once report both
    — the two checks are independent, not an if/else."""
    other = "plan/_trains/probe-subject/other.yaml"
    root = _materialize(
        tmp_path,
        rows=[_row(_TID, _REL)],
        documents={other: _doc("train:probe-subject:other")},
    )

    directions = sorted(v["direction"] for v in registry_violations(root))

    assert directions == ["dangling", "orphan"]


@pytest.mark.platform
def test_every_emitted_evidence_key_is_declared_by_the_convention_node(tmp_path):
    """Evidence the node does not declare cannot be acted on by a consumer.

    Reads atdd's OWN convention node, which is a toolkit-source fact absent when
    atdd is an installed package — hence `platform`, as on the sibling rule.
    """
    root = _materialize(
        tmp_path,
        rows=[_row(_TID, _REL)],
        documents={"plan/_trains/probe-subject/other.yaml": _doc("train:probe-subject:other")},
    )
    node = find_repo_root() / _NODES_DIR / f"{_RULE_ID}.convention.yaml"
    doc = yaml.safe_load(node.read_text(encoding="utf-8"))
    declared = set((doc.get("validation") or {}).get("failure_evidence") or [])

    violations = registry_violations(root)
    assert violations, "the probe emitted nothing — the evidence check proved nothing"
    for v in violations:
        assert set(v) <= declared, f"undeclared evidence keys: {set(v) - declared}"


@pytest.mark.platform
def test_the_node_binds_this_module_rather_than_a_reference_resolver():
    """#1942's root cause, guarded: the node claimed a spec file must exist but
    pointed at a train→wagon reference resolver, and the binding gate exempts
    convention-variant refs from the bind_rule check, so nothing complained.
    """
    node = find_repo_root() / _NODES_DIR / f"{_RULE_ID}.convention.yaml"
    doc = yaml.safe_load(node.read_text(encoding="utf-8"))
    ref = (doc.get("implementation") or {}).get("ref", "")

    assert ref.startswith("test_train_registry_coherence::"), (
        f"{_RULE_ID} names {ref!r}, which does not resolve to this module; the "
        "rule's existence claim would be inert again"
    )
    assert _RULE.rule_id == _RULE_ID
