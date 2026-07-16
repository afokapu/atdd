"""Import `.atdd/manifest.yaml` operational state into the State Store (#1183).

#1168 Phase 4 (import half). Reads the manifest's ``sessions`` ledger and writes
each entry into the State Store through the Phase-3 typed APIs (#1182) — never
raw SQL — as a ``work_item`` object keyed by its **slug** (the stable local
identity), with the GitHub issue number recorded as an ``external_ref`` (a
projection, not the identity). A backup is written to
``.atdd/manifest.migrated.yaml``.

This module is **additive**: it does not yet stop manifest writes or reroute
``atdd issue`` through the store — that behavioural rewiring is a deliberate
follow-up so the lifecycle everything depends on changes in isolation. Import is
idempotent (upsert), so it can run repeatedly while both stores coexist.

Dependency note: unlike the stdlib-only resolver/db/store modules, this importer
uses PyYAML (a core project dependency) to read the manifest. It still MUST NOT
import ``atdd.coach.*`` / ``atdd.train.*`` / ``atdd.integrations.*``.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from atdd.state.db import connect, init_state_store
from atdd.state.paths import ATDD_DIR, resolve_control_root
from atdd.state.store import StateStore

_log = logging.getLogger(__name__)

WORK_ITEM_KIND = "work_item"
GITHUB_PROVIDER = "github"
#: Manifest keys mapped to dedicated columns rather than the JSON ``data`` bag.
_IDENTITY_KEY = "slug"
_STATE_KEY = "status"
_BACKUP_NAME = "manifest.migrated.yaml"


@dataclass(frozen=True)
class ImportResult:
    imported: int
    external_refs: int
    skipped: int
    db_path: Path
    backup_path: Path
    skipped_reasons: List[str]
    #: Duplicate GitHub issue_numbers across slugs (one issue → many work items).
    #: First-in-manifest-order wins the external ref; later ones are reported here.
    collisions: List[str]


def _manifest_path(control_root: Path) -> Path:
    return control_root / ATDD_DIR / "manifest.yaml"


def import_manifest(
    control_root: Optional[Path] = None,
    *,
    db_path: Optional[Path] = None,
    manifest_path: Optional[Path] = None,
) -> ImportResult:
    """Import the manifest ledger into the State Store; write a backup.

    ``control_root`` (default: resolved from cwd) locates both the manifest and
    the store. ``db_path`` / ``manifest_path`` override locations for tests.
    Idempotent: each entry is upserted by slug.
    """
    if control_root is not None:
        root = Path(control_root)
    elif manifest_path is not None:
        # manifest_path is <root>/.atdd/manifest.yaml
        root = Path(manifest_path).resolve().parent.parent
    else:
        root = resolve_control_root(Path.cwd()).control_root

    manifest = Path(manifest_path) if manifest_path is not None else _manifest_path(root)
    if not manifest.is_file():
        raise FileNotFoundError(f"manifest not found: {manifest}")

    store_db = init_state_store(db_path=db_path) if db_path is not None else init_state_store(start=root)

    doc = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
    sessions: List[Dict[str, Any]] = doc.get("sessions") or []

    imported = ext_count = skipped = 0
    skipped_reasons: List[str] = []
    collisions: List[str] = []
    seen_issue: Dict[str, str] = {}  # issue_number(str) -> first slug that claimed it

    conn = connect(store_db)
    try:
        store = StateStore(conn)
        for entry in sessions:
            slug = entry.get(_IDENTITY_KEY)
            if not slug:
                skipped += 1
                skipped_reasons.append(f"entry without slug: id={entry.get('id')}")
                continue
            state = entry.get(_STATE_KEY)
            data = {k: v for k, v in entry.items() if k not in (_IDENTITY_KEY, _STATE_KEY)}
            # noqa: N+1 — a one-time bulk manifest import is inherently one upsert per
            # ledger entry through the typed store API; not an avoidable query-in-loop.
            store.objects.upsert(slug, WORK_ITEM_KIND, state=state, data=data)  # noqa: N+1
            imported += 1

            issue_number = entry.get("issue_number")
            if issue_number is None:
                continue
            ref_value = str(issue_number)
            first = seen_issue.get(ref_value)
            if first is not None:
                # One GitHub issue maps to one work item: keep the first claimant,
                # report the duplicate rather than silently reassigning the ref.
                collisions.append(f"issue #{ref_value}: kept '{first}', not re-linked to '{slug}'")
                continue
            seen_issue[ref_value] = slug
            store.external_refs.link(  # noqa: N+1 — bulk import, one ref per entry (see above)
                slug, GITHUB_PROVIDER, "issue", ref_value, data={"source": "manifest-import"},
            )
            ext_count += 1
    finally:
        conn.close()

    backup = root / ATDD_DIR / _BACKUP_NAME
    backup.write_text(manifest.read_text(encoding="utf-8"), encoding="utf-8")

    _log.info(
        "manifest imported into State Store",
        extra={"imported": imported, "external_refs": ext_count, "skipped": skipped,
            "collisions": len(collisions), "db": str(store_db), "backup": str(backup)},
    )
    return ImportResult(
        imported=imported, external_refs=ext_count, skipped=skipped,
        db_path=store_db, backup_path=backup, skipped_reasons=skipped_reasons,
        collisions=collisions,
    )
