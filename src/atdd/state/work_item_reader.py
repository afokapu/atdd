"""Store-backed work-item reader — the #1203 Phase 1 shadow-read facade.

#1168 Phase 4 (behavioural cutover, read half). Routes ``atdd issue`` work-item
reads through the State Store instead of parsing ``.atdd/manifest.yaml`` directly.
Work items are keyed in the store by their **slug** (the stable local identity),
so this facade resolves a GitHub ``issue_number`` to its work item through the
``external_refs`` projection (provider ``github`` / ref_kind ``issue``) before
reading status/train/branch off the stored object.

Decision #3 (single import path): if the store holds no ``work_item`` objects on
first read, the manifest is imported once via the #1183 ``import_manifest`` path,
then the store is authoritative for the read. A missing manifest is tolerated —
reads simply return ``None`` (an unregistered issue is valid and must not crash
the lifecycle).

This module is the **read** half only; it makes no operational writes (the
authoritative-write cutover is Phase 2). Dependency discipline: stdlib +
``atdd.state`` only — it MUST NOT import ``atdd.coach.*`` (it is the foundational
layer the lifecycle command consumes, not the reverse).
"""
from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from types import TracebackType
from typing import Optional, Type

from atdd.state.db import connect, init_state_store
from atdd.state.manifest_import import GITHUB_PROVIDER, WORK_ITEM_KIND, import_manifest
from atdd.state.paths import ATDD_DIR, resolve_control_root
from atdd.state.store import Object, StateStore

_log = logging.getLogger(__name__)

#: ``external_refs.ref_kind`` for the GitHub issue projection (#1183).
_ISSUE_REF_KIND = "issue"
#: Work-item ``data`` keys mirrored from the manifest session entry.
_TRAIN_KEY = "train"
_BRANCH_KEY = "branch"
_WAGON_KEY = "wagon"
_FEATURE_KEY = "feature"


class WorkItemReader:
    """Read work-item lifecycle state from the State Store, keyed by issue number.

    Open with a Control Root (default: resolved from cwd); ``db_path`` /
    ``manifest_path`` override locations for tests. Holds one read connection for
    its lifetime — use it as a context manager (or call :meth:`close`)::

        with WorkItemReader(control_root=repo) as reader:
            status = reader.status(1203)

    The store is migrated and (if empty) imported from the manifest at
    construction, so every read after that is a pure store query.
    """

    def __init__(
        self,
        control_root: Optional[Path] = None,
        *,
        db_path: Optional[Path] = None,
        manifest_path: Optional[Path] = None,
    ) -> None:
        if control_root is not None:
            self._root: Optional[Path] = Path(control_root)
        elif manifest_path is not None:
            self._root = Path(manifest_path).resolve().parent.parent
        else:
            try:
                self._root = resolve_control_root(Path.cwd()).control_root
            except Exception:  # noqa: BLE001 — no Control Root is a tolerable read miss
                self._root = None

        self._manifest_path = (
            Path(manifest_path)
            if manifest_path is not None
            else (self._root / ATDD_DIR / "manifest.yaml" if self._root is not None else None)
        )

        # Ensure the store exists + is migrated, then auto-import once if empty.
        if db_path is not None:
            self._db_path: Path = init_state_store(db_path=Path(db_path))
        else:
            self._db_path = init_state_store(start=self._root)
        self._auto_import_if_empty(db_path=db_path)

        self._conn: sqlite3.Connection = connect(self._db_path)
        self._store = StateStore(self._conn)

    # -- lifecycle ---------------------------------------------------------- #
    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "WorkItemReader":
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc: Optional[BaseException],
        tb: Optional[TracebackType],
    ) -> None:
        self.close()

    # -- reads -------------------------------------------------------------- #
    def get(self, issue_number: int) -> Optional[Object]:
        """The stored work-item object for ``issue_number``, or ``None``.

        Resolves issue_number → slug via the GitHub ``external_ref`` projection,
        then loads the object by its slug uid.
        """
        ref = self._store.external_refs.resolve(
            GITHUB_PROVIDER, _ISSUE_REF_KIND, str(issue_number)
        )
        if ref is None:
            return None
        return self._store.objects.get(ref.object_uid)

    def status(self, issue_number: int) -> Optional[str]:
        """The lifecycle phase (the object ``state``) for ``issue_number``."""
        obj = self.get(issue_number)
        return obj.state if obj is not None else None

    def train(self, issue_number: int) -> Optional[str]:
        """The train recorded for ``issue_number`` (from the work-item ``data``)."""
        obj = self.get(issue_number)
        return obj.data.get(_TRAIN_KEY) if obj is not None else None

    def branch(self, issue_number: int) -> Optional[str]:
        """The branch recorded for ``issue_number`` (from the work-item ``data``)."""
        obj = self.get(issue_number)
        return obj.data.get(_BRANCH_KEY) if obj is not None else None

    def wagon(self, issue_number: int) -> Optional[str]:
        """The wagon slug recorded for ``issue_number`` (from the work-item ``data``)."""
        obj = self.get(issue_number)
        return obj.data.get(_WAGON_KEY) if obj is not None else None

    def issue_wagon_map(self) -> dict[int, str]:
        """Map GitHub issue number → wagon slug for every stored work item with a wagon.

        The store-backed analog of scanning the manifest ``sessions`` for
        ``issue_number``/``wagon`` pairs: enumerate the GitHub ``issue``
        external-refs and read each linked work item's wagon from its ``data``
        bag. Items with no wagon (or a non-integer ref) are skipped, so the map
        holds only issues that actually carry a wagon.
        """
        out: dict[int, str] = {}
        for ref in self._store.external_refs.all():
            if ref.provider != GITHUB_PROVIDER or ref.ref_kind != _ISSUE_REF_KIND:
                continue
            obj = self._store.objects.get(ref.object_uid)
            if obj is None:
                continue
            wagon = obj.data.get(_WAGON_KEY)
            if not wagon:
                continue
            try:
                out[int(ref.ref_value)] = str(wagon)
            except (TypeError, ValueError):
                continue
        return out

    def feature(self, issue_number: int) -> Optional[str]:
        """The feature URN recorded for ``issue_number`` (from the work-item ``data``)."""
        obj = self.get(issue_number)
        return obj.data.get(_FEATURE_KEY) if obj is not None else None

    def issue_number_for_slug(self, slug: str) -> Optional[int]:
        """Reverse lookup: the GitHub issue number linked to work-item *slug*, or None.

        The store keys work items by slug (the object uid) and links exactly one
        GitHub ``issue`` external-ref per issue, so this is unambiguous — unlike
        the manifest scan it replaces, which had to pick the last duplicate slug.
        """
        for ref in self._store.external_refs.for_object(slug):
            if ref.provider == GITHUB_PROVIDER and ref.ref_kind == _ISSUE_REF_KIND:
                try:
                    return int(ref.ref_value)
                except (TypeError, ValueError):
                    _log.debug(
                        "non-integer github issue ref_value; treating slug as unlinked",
                        extra={"slug": slug, "ref_value": ref.ref_value},
                    )
                    return None
        return None

    def session_entry(self, issue_number: int) -> Optional[dict]:
        """Reconstruct the manifest-``sessions``-shaped dict for ``issue_number``.

        Returns ``{**data, "slug": <uid>, "status": <state>}`` — the same shape
        the manifest carried — so callers that read ``entry["slug"]`` /
        ``entry.get("type")`` off a manifest session keep working unchanged, now
        sourced from the store. Returns ``None`` for an unregistered issue.
        """
        obj = self.get(issue_number)
        if obj is None:
            return None
        return {**obj.data, "slug": obj.uid, "status": obj.state}

    def all_work_items(self) -> list[dict]:
        """Every work item as a manifest-``sessions``-shaped dict, from the store.

        The store-backed analog of scanning the manifest ``sessions`` list:
        returns ``{**data, "slug": <uid>, "status": <state>, "issue_number": <n>}``
        for every ``work_item`` object, with the GitHub issue number folded in
        from the ``external_refs`` projection (omitted when the item carries no
        GitHub ref). Returns ``[]`` on any store error so callers that scanned a
        possibly-absent manifest keep their fail-closed behaviour unchanged.
        """
        try:
            by_uid: dict[str, int] = {}
            for ref in self._store.external_refs.all():
                if ref.provider == GITHUB_PROVIDER and ref.ref_kind == _ISSUE_REF_KIND:
                    try:
                        by_uid[ref.object_uid] = int(ref.ref_value)
                    except (TypeError, ValueError):
                        continue
            rows: list[dict] = []
            for obj in self._store.objects.list(kind=WORK_ITEM_KIND):
                entry = {**obj.data, "slug": obj.uid, "status": obj.state}
                if obj.uid in by_uid:
                    entry["issue_number"] = by_uid[obj.uid]
                rows.append(entry)
            return rows
        except Exception as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
            _log.debug("all_work_items unavailable; returning empty", extra={"error": str(exc)})
            return []

    # -- internals ---------------------------------------------------------- #
    def _auto_import_if_empty(self, *, db_path: Optional[Path]) -> None:
        """Import the manifest into the store once, only when the store is empty.

        Idempotent in effect: a non-empty store is left untouched, so the import
        runs at most once per store (Decision #3). A missing manifest is a no-op
        — reads then return ``None`` rather than raising.
        """
        conn = connect(self._db_path)
        try:
            empty = not StateStore(conn).objects.list(kind=WORK_ITEM_KIND)
        finally:
            conn.close()
        if not empty:
            return
        if self._manifest_path is None or not self._manifest_path.is_file():
            return
        import_manifest(
            control_root=self._root,
            db_path=db_path,
            manifest_path=self._manifest_path,
        )
        _log.info(
            "work-item store empty — imported manifest on first read",
            extra={"manifest": str(self._manifest_path), "db": str(self._db_path)},
        )
