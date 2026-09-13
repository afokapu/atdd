# URN: test:author-plan-substrate:author-train:E004-UNIT-008-document-precedes-registry
# Acceptance: acc:author-plan-substrate:E004-UNIT-008-document-precedes-registry
# WMBT: wmbt:author-plan-substrate:E004
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""E004-UNIT-008 (#1942) — create_train writes the document before the registry.

``create_train`` upserted the registry FIRST and wrote the per-train document
second, while its siblings ``create_contract`` and ``create_interlocking`` write
the document first. A failure between the two writes therefore left residue whose
shape depended on which writer happened to run:

* ``create_train``    → a ``plan/_trains.yaml`` row naming a file that is not on disk
* ``create_contract`` → a schema file on disk that no registry row names

The two are not equally bad. An orphan document is inert: nothing resolves through
it, and a coherence scan can find it. A registry row naming an absent document is a
dangling pointer every consumer walks into — measured on the real corpus, it turns
``test_route_space_admission`` into a bare ``FileNotFoundError`` with no rule id and
no fix hint, so the gate stops reporting the defect and starts crashing on it.

**The failure is induced, never mocked.** A directory is planted at the exact path
the document write targets, so the writer's own ``open(..., "w")`` raises
``IsADirectoryError`` from inside ``_write_yaml``. That stands in for any
second-write failure — ``ENOSPC``, ``EACCES``, a refused authoring review — without
patching the module under test, so the test constrains the real call order rather
than a stubbed stand-in for it.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from atdd.planner.commands.author import AuthorInputError, create_train

_TRAIN_ID = "train:author-plan-substrate:ordering-probe"


def _spec() -> dict:
    return {
        "train_id": _TRAIN_ID,
        "category": "nominal",
        "title": "Ordering probe",
        "description": "a typed train for the write-ordering guard",
        "themes": ["plan"],
        "sequence": [],
        "wagons": [],
    }


def _plan_home(tmp_path: Path) -> Path:
    plan = tmp_path / "plan"
    (plan / "_trains").mkdir(parents=True)
    (plan / "_trains.yaml").write_text("trains: {}\n", encoding="utf-8")
    return plan


def _rows_naming(registry_path: Path, train_id: str) -> list:
    """Every registry row carrying ``train_id``, across every theme/category bucket."""
    if not registry_path.is_file():
        return []
    registry = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}
    rows = []
    for buckets in (registry.get("trains") or {}).values():
        for entries in (buckets or {}).values():
            for entry in entries or []:
                if isinstance(entry, dict) and entry.get("train_id") == train_id:
                    rows.append(entry)
    return rows


def test_a_failed_document_write_leaves_no_registry_row(tmp_path):
    """The defect itself: the registry must not outlive a failed document write."""
    plan = _plan_home(tmp_path)
    doc_path = plan / "_trains" / "author-plan-substrate" / "ordering-probe.yaml"
    # Plant a directory where the document goes: the writer's open() now raises.
    doc_path.mkdir(parents=True)

    with pytest.raises(OSError):
        create_train(_spec(), root=tmp_path)

    rows = _rows_naming(plan / "_trains.yaml", _TRAIN_ID)
    assert rows == [], (
        "create_train left a registry row naming a document it failed to write "
        f"({rows}) — a dangling pointer every consumer resolves through"
    )


def test_the_document_is_written_before_the_registry_is_touched(tmp_path):
    """Ordering stated positively, so the guard survives a refactor of the failure
    path: at the moment the registry is written, the document must already exist."""
    plan = _plan_home(tmp_path)
    registry_path = plan / "_trains.yaml"
    doc_path = plan / "_trains" / "author-plan-substrate" / "ordering-probe.yaml"
    observed: list[bool] = []

    # Observe the filesystem, not the call sequence: a write-order assertion that
    # watches real on-disk state cannot be satisfied by reordering statements that
    # do not actually change what survives a crash.
    import atdd.planner.commands.author as author_mod

    real_write_yaml = author_mod._write_yaml

    def watching_write_yaml(path, doc, **kwargs):
        if Path(path) == registry_path:
            observed.append(doc_path.is_file())
        return real_write_yaml(path, doc, **kwargs)

    author_mod._write_yaml = watching_write_yaml
    try:
        create_train(_spec(), root=tmp_path)
    finally:
        author_mod._write_yaml = real_write_yaml

    assert observed, "the registry was never written — the probe did not run"
    assert all(observed), (
        "the registry was written while the per-train document did not yet exist; "
        "the document must be written first so a failure can only orphan a file"
    )


def test_a_refused_author_writes_neither_artifact(tmp_path):
    """Ordering must not cost the writer its validate-before-write property.

    Moving the registry write second drags its shape guard along unless the guard
    is hoisted deliberately. If it is not, a refused legacy-shape author starts
    leaving the per-train document behind — the partial tree this reorder exists
    to prevent, reintroduced through the front door. E004-UNIT-001 catches the
    legacy-shape case; this states the invariant where the ordering lives.
    """
    plan = tmp_path / "plan"
    (plan / "_trains").mkdir(parents=True)
    # A pre-#1421 list-shaped registry: the upsert refuses it.
    (plan / "_trains.yaml").write_text(
        "trains:\n- train_id: train:legacy:old-shape\n", encoding="utf-8")

    with pytest.raises(AuthorInputError) as exc:
        create_train(_spec(), root=tmp_path)
    assert exc.value.field == "registry"

    assert not (plan / "_trains" / "author-plan-substrate").exists(), (
        "a refused author wrote the per-train document before validating the "
        "registry it was going to write into"
    )


def test_the_happy_path_still_writes_both_artifacts(tmp_path):
    """Reordering must not cost the writer its actual job."""
    plan = _plan_home(tmp_path)

    per_train = create_train(_spec(), root=tmp_path)

    assert per_train.is_file()
    rows = _rows_naming(plan / "_trains.yaml", _TRAIN_ID)
    assert len(rows) == 1, rows
    # The row's path must resolve — the invariant the coherence validator polices.
    assert (tmp_path / rows[0]["path"]).is_file()
