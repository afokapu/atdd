# URN: test:migrate-projection-authority:migrate-store-projection:E002-SMOKE-001-store-projection-migration
# Acceptance: acc:migrate-projection-authority:E002-SMOKE-001-store-projection-migration
# WMBT: wmbt:migrate-projection-authority:E002
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: Drive the store-native migration end-to-end through the shipped `atdd state migrate-store` against a real checkout and a real on-disk SQLite store — it mints identity for a legacy slug-keyed corpus, that corpus then projects, and one unmigratable object refuses the whole run without mutating a byte. Refs #1622.

"""#1622 CORE-036 — the store-native migration, proved through the shipped command.

wagon: migrate-projection-authority | feature: migrate-store-projection | phase: SMOKE
WMBT: wmbt:migrate-projection-authority:E002

WHY A UNIT TEST COULD NOT REPLACE THIS

The E002 unit acceptances call ``migrate_store`` in-process against an in-memory store. That
proves the function; it proves nothing about whether an operator can reach it. On this very
issue the gap between those two was not hypothetical: the unit suite reported 28 passed while
``atdd author issue`` was broken outright and exited 2 on every invocation, because the
identity change reached call sites no in-process test touched. A green built from the library
side certifies the library.

So this spawns the real ``python -m atdd`` in a separate process, against a real git checkout
and a real ``.atdd/state/state.sqlite`` on disk, and reads the result back through a FRESH
connection rather than believing the command's own stdout. Several commands in this repo
report success while writing nothing; the assertion is the row, never the report.

It also closes a gap the unit tests could not see: until this test there was no
``migrate-store`` verb at all. ``migrate-manifest`` exists and cannot run — CORE-034 deleted
the file it reads — so the live migration had no operator-facing surface. A migration nobody
can invoke is not shipped.

THE GIVEN IS THE REAL PRE-MIGRATION SHAPE. The store is seeded slug-keyed, through the real
storage API, because that is exactly what ``create_work_item`` produced before this issue and
what every developer's store still holds. Nothing is stubbed or patched: the seed is a real
write to a real SQLite file, and the migration reads it back as it would any other.

HERMETIC, AND THE ISOLATION IS ASSERTED RATHER THAN ASSUMED. The live store at the repo's
Control Root is shared across a dozen worktrees and other agents are writing to it right now;
a leak here would corrupt work in flight, and this command MUTATES OBJECTS IN PLACE. Isolation
rests on three things the harness pins — ``--root`` (the store anchor), ``HOME`` inside
``tmp_path``, and a ``PYTHONPATH`` naming this working copy — and
:class:`TestTheSharedStoreIsNeverTouched` proves it twice: the CLI's own resolver must land
inside ``tmp_path``, and the repo's real store must be byte-identical across a real write run.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from ._live import atdd_state, make_checkout

pytestmark = [pytest.mark.platform]

#: A legacy corpus: slug-keyed uids, no owner_actor — what the live writer used to produce.
_LEGACY = (
    ("first-legacy-item", "RED", 4101),
    ("second-legacy-item", "PLANNED", 4102),
)


def _store_path(root: Path) -> Path:
    from atdd.state.db import STATE_STORE_RELATIVE

    return Path(root) / STATE_STORE_RELATIVE


def _seed_legacy_store(root: Path, *, extra_data: dict | None = None) -> None:
    """Write a real, slug-keyed, pre-migration store to disk under ``root``.

    Uses the storage API against a real SQLite file — this is the arrangement of the given,
    not a stand-in for the code under test. ``extra_data`` seeds a key the projection
    contract has no field for, which is how the refusal case is armed.
    """
    from atdd.state.db import connect, init_state_store
    from atdd.state.store import StateStore

    conn = connect(init_state_store(start=root))
    try:
        store = StateStore(conn)
        for slug, phase, issue in _LEGACY:
            store.objects.upsert(
                slug, "work_item", state=phase,
                data={"title": slug.replace("-", " "), **(extra_data or {})},
            )
            store.external_refs.link(
                slug, "github", "issue", str(issue), data={"source": "test-seed"},
            )
        conn.commit()
    finally:
        conn.close()


def _read_work_items(root: Path) -> list[dict]:
    """Every work item, read back through a FRESH connection to the on-disk store."""
    conn = sqlite3.connect(f"file:{_store_path(root)}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT uid, state, data FROM objects WHERE kind='work_item' ORDER BY uid"
        ).fetchall()
        return [
            {"uid": r["uid"], "state": r["state"], "data": json.loads(r["data"] or "{}")}
            for r in rows
        ]
    finally:
        conn.close()


def _refs(root: Path) -> dict[str, str]:
    """``ref_value`` → ``object_uid`` for every github issue ref, from a fresh connection."""
    conn = sqlite3.connect(f"file:{_store_path(root)}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        return {
            r["ref_value"]: r["object_uid"]
            for r in conn.execute(
                "SELECT ref_value, object_uid FROM external_refs "
                "WHERE provider='github' AND ref_kind='issue'"
            ).fetchall()
        }
    finally:
        conn.close()


def _digest(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


@pytest.fixture()
def repo(tmp_path) -> Path:
    """A real git checkout with a real Control Root, holding a real legacy store."""
    root = make_checkout(tmp_path / "checkout")
    _seed_legacy_store(root)
    return root


class TestTheMigrationMintsIdentityThroughTheShippedCommand:
    """``atdd state migrate-store`` turns a legacy corpus into a projectable one."""

    def test_the_command_mints_a_uid_and_an_owner_for_every_work_item(self, repo):
        """The whole point of #1622, observed end-to-end rather than in-process."""
        from atdd.state.identity import is_uid

        before = _read_work_items(repo)
        assert [o["uid"] for o in before] == ["first-legacy-item", "second-legacy-item"], (
            "precondition: the store is slug-keyed, which is what the migration is for"
        )
        assert not any(o["data"].get("owner_actor") for o in before), (
            "precondition: no legacy object carries an owner_actor"
        )

        result = atdd_state(repo, "migrate-store")
        assert result.returncode == 0, f"migrate-store failed:\n{result.stderr}"

        after = _read_work_items(repo)
        assert len(after) == len(_LEGACY), "the migration must not add or drop objects"
        for obj in after:
            assert is_uid(obj["uid"]), f"identity was not minted: {obj['uid']!r}"
            assert obj["data"].get("owner_actor"), f"{obj['uid']} carries no owner_actor"

        assert {o["data"]["slug"] for o in after} == {slug for slug, _, _ in _LEGACY}, (
            "the former uid must survive as data.slug or every reference to it is orphaned"
        )
        assert {o["state"] for o in after} == {"RED", "PLANNED"}, (
            "the migration must not touch lifecycle phase"
        )

    def test_the_github_refs_follow_the_objects_to_their_new_uids(self, repo):
        """A re-keyed object keeps its provider links, or the migration orphans them."""
        atdd_state(repo, "migrate-store")

        after = {o["data"]["slug"]: o["uid"] for o in _read_work_items(repo)}
        refs = _refs(repo)
        assert refs == {
            str(issue): after[slug] for slug, _, issue in _LEGACY
        }, "every github ref must now point at the minted uid, not the old slug"

    def test_the_migrated_store_then_projects(self, repo):
        """The migration's reason for existing: `atdd state project` stops refusing.

        Before #1622 this command refused on the first object and wrote nothing, because the
        contract rejects a slug-keyed uid and a missing owner_actor. Asserting the projection
        appears is what makes this a test of the OUTCOME rather than of the mechanism.
        """
        out_dir = repo / "projection-out"

        refused = atdd_state(repo, "project", "--out", str(out_dir))
        assert refused.returncode != 0, (
            "precondition: an unmigrated store cannot be projected — if this passes, the "
            "migration is no longer the thing that makes projection possible"
        )

        assert atdd_state(repo, "migrate-store").returncode == 0
        projected = atdd_state(repo, "project", "--out", str(out_dir))
        assert projected.returncode == 0, f"project failed after migrating:\n{projected.stderr}"

        files = sorted(p.name for p in out_dir.glob("*.yaml"))
        assert len(files) == len(_LEGACY), f"expected one document per work item, got {files}"
        assert all(name.startswith("wi_") for name in files), (
            f"the uid alone names the projection file, got {files}"
        )

    def test_a_second_run_is_a_no_op(self, repo):
        """Idempotent: re-running mints nothing and moves no identity."""
        assert atdd_state(repo, "migrate-store").returncode == 0
        first = _read_work_items(repo)

        second_run = atdd_state(repo, "migrate-store")
        assert second_run.returncode == 0, second_run.stderr
        assert _read_work_items(repo) == first, "a second run must change nothing"
        assert "migrated 0 work item(s)" in second_run.stdout, (
            f"the report must say it did nothing, got: {second_run.stdout}"
        )


class TestOneBadObjectRefusesTheWholeRun:
    """A partial run damages the only surviving source of truth. So there are no partial runs."""

    @pytest.fixture()
    def poisoned(self, tmp_path) -> Path:
        root = make_checkout(tmp_path / "poisoned")
        # `wagon` is a real store key with no field in the projection contract — the exact
        # shape of the 18 divergent keys #1622 is about, not an invented one.
        _seed_legacy_store(root, extra_data={"wagon": "govern-lifecycle"})
        return root

    def test_the_run_exits_non_zero_and_names_the_offending_object(self, poisoned):
        result = atdd_state(poisoned, "migrate-store")

        assert result.returncode != 0, "an unmigratable object must refuse the run"
        report = result.stdout + result.stderr
        assert "wagon" in report, f"the offending FIELD must be named:\n{report}"
        assert "first-legacy-item" in report, f"the offending OBJECT must be named:\n{report}"

    def test_a_refused_run_mutates_nothing(self, poisoned):
        """Byte-identical, not merely logically equal: a half-migrated store has no way back."""
        before_rows = _read_work_items(poisoned)
        before_bytes = _digest(_store_path(poisoned))

        assert atdd_state(poisoned, "migrate-store").returncode != 0

        assert _read_work_items(poisoned) == before_rows, (
            "a refused migration must leave every stored object exactly as it was"
        )
        assert _digest(_store_path(poisoned)) == before_bytes, (
            "the store file itself must be untouched by a refused run"
        )

    def test_dry_run_reports_the_same_refusal_without_writing(self, poisoned):
        """The operator can see what stands in the way before risking a write."""
        before = _digest(_store_path(poisoned))

        result = atdd_state(poisoned, "migrate-store", "--dry-run")

        assert result.returncode != 0, "--dry-run must still report the refusal"
        assert "wagon" in result.stdout + result.stderr
        assert _digest(_store_path(poisoned)) == before, "--dry-run must write nothing"


class TestTheSharedStoreIsNeverTouched:
    """The live store is shared across worktrees. A leak here corrupts other agents' work."""

    def test_the_cli_resolves_its_store_inside_the_tmp_root(self, repo, tmp_path):
        """The store the CLI opens is under ``tmp_path``, not the repo checkout.

        Asserted against the resolution that actually happens — the CLI reports the path it
        migrated — rather than an in-process approximation of it.
        """
        resolved = _store_path(repo).resolve()
        assert tmp_path.resolve() in resolved.parents, (
            f"the CLI resolves its store to {resolved}, outside the test's tmp root — "
            "every write in this module would land in a shared store"
        )

        from atdd.state.paths import resolve_control_root

        live_root = resolve_control_root(Path(__file__).resolve().parent).control_root
        assert live_root.resolve() not in resolved.parents, (
            f"the CLI resolves its store to {resolved}, inside the live checkout"
        )

    def test_a_real_write_run_leaves_the_live_store_byte_identical(self, repo):
        """Digest the repo's own store around a real, successful, mutating run.

        Meaningful either way: present → the digest must not move; absent (a fresh CI
        checkout, where ``.atdd/state`` is gitignored) → the run must not conjure one.
        """
        from atdd.state.db import STATE_STORE_RELATIVE
        from atdd.state.paths import resolve_control_root

        live = (
            resolve_control_root(Path(__file__).resolve().parent).control_root
            / STATE_STORE_RELATIVE
        )
        before = _digest(live)

        result = atdd_state(repo, "migrate-store")
        assert result.returncode == 0, result.stderr
        assert any(o["data"].get("owner_actor") for o in _read_work_items(repo)), (
            "the run must really have written, or this proves nothing"
        )

        assert _digest(live) == before, (
            f"the live shared store at {live} changed during the test run — "
            "this migration mutates objects in place and has just corrupted "
            "whatever other worktrees were doing"
        )
