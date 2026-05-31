"""Shared helpers for the E040 (#894) train.persistence tests.

Builds a self-contained temp ATDD repo (manifest + canonical phase-machine YAML)
so ``JsonlPersistenceStore`` / ``load_conventions`` / ``materialize_evidence`` can
be exercised against a real on-disk root without touching the live repo.

Not a test module (leading underscore) — pytest does not collect it.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import yaml

import atdd

# The canonical §4.5 phase machine shipped with the package (Child 1).
_PHASE_MACHINE_SRC = (
    Path(atdd.__file__).resolve().parent
    / "coach"
    / "conventions"
    / "phase_machine.convention.yaml"
)


def build_temp_repo(
    root: Path,
    *,
    issue_number: int = 894,
    slug: str = "extract-workflow-persistence-and-events-schema",
    status: str = "GREEN",
    issue_type: str = "implementation",
    train: str | None = "0001-self-compliance-validate",
) -> Path:
    """Materialize a minimal ATDD repo under ``root`` and return ``root``.

    Writes ``.atdd/manifest.yaml`` (one session for ``issue_number``) and copies
    the real phase-machine convention YAML to the in-repo location so
    ``load_conventions(root)`` resolves from the repo root.
    """
    atdd_dir = root / ".atdd"
    atdd_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "version": "2.0",
        "created": "2026-05-31",
        "sessions": [
            {
                "id": str(issue_number),
                "slug": slug,
                "file": None,
                "issue_number": issue_number,
                "type": issue_type,
                "status": status,
                "train": train,
                "created": "2026-05-31",
                "archived": None,
                "wagon": "govern-lifecycle",
            }
        ],
    }
    (atdd_dir / "manifest.yaml").write_text(yaml.safe_dump(manifest, sort_keys=False))

    conv_dir = root / "src" / "atdd" / "coach" / "conventions"
    conv_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(_PHASE_MACHINE_SRC, conv_dir / "phase_machine.convention.yaml")
    return root
