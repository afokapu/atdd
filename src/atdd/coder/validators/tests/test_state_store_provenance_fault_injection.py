# URN: component:govern-lifecycle:enforcement-substrate:provenance_fault_injection:backend:tests
# Runtime: python
# Purpose: Prove the #1557 provenance VALIDATOR can fail — not merely that the
#          audit function beneath it can. A validator that cannot emit passes
#          forever, and the live corpus is currently advisory, so the rule's
#          clean-run pass says nothing on its own.

"""Fault injection for ``scan_work_item_provenance`` (#1557).

``src/atdd/state/tests/test_provenance.py`` proves the *audit* reports each
clause. This module proves the *validator wrapper* does its two jobs: it turns
findings into :class:`Violation` rows carrying the right rule_id, and it fails
closed when the store cannot be read.

Both matter independently. A wrapper that swallowed the audit's findings, or one
that caught :class:`ProvenanceStoreUnreadable` and returned ``[]``, would leave
the rule green forever while the invariant it names went unenforced — which is
exactly the fail-open posture (#1557) exists to replace.

Hermetic: every probe builds its own throwaway Control Root. The developer's
live store is never touched.
"""
from __future__ import annotations

import pytest

from atdd.coder.validators.test_state_store_invariants import (
    scan_work_item_provenance,
)
from atdd.state import provenance
from atdd.state.db import connect, init_state_store
from atdd.state.manifest_import import WORK_ITEM_KIND
from atdd.state.store import StateStore


def _control_root(tmp_path):
    """A throwaway Control Root.

    ``.atdd/`` alone is scratch (#1179) — the resolver wants an *initialized*
    root, which ``config.yaml`` signals.
    """
    (tmp_path / ".atdd").mkdir()
    (tmp_path / ".atdd" / "config.yaml").write_text("{}\n", encoding="utf-8")
    return tmp_path


def _seed(root, uid: str, stamp: str = "none"):
    """Create one work item in ``root``'s store with the given provenance."""
    conn = connect(init_state_store(start=root))
    try:
        store = StateStore(conn)
        store.objects.upsert(uid, WORK_ITEM_KIND, state="INIT")
        if stamp == "authored":
            provenance.record_authored(store, uid, command="atdd author issue")
        elif stamp == "reconciled":
            provenance.record_reconciled(
                store, uid, discovered_via="atdd coach reconcile"
            )
    finally:
        conn.close()


# --------------------------------------------------------------------------- #
# The validator can FAIL
# --------------------------------------------------------------------------- #
@pytest.mark.coder
def test_scan_emits_a_violation_for_an_unprovenanced_work_item(tmp_path):
    """An out-of-band create surfaces as a rule-bound Violation, not silence."""
    root = _control_root(tmp_path)
    _seed(root, "wi-out-of-band", stamp="none")

    violations = scan_work_item_provenance(control_root=root)

    assert len(violations) == 1
    assert violations[0].rule_id == "coder.state-store.work-item-provenance"
    assert "wi-out-of-band" in violations[0].location


@pytest.mark.coder
def test_scan_emits_a_violation_for_a_reconciled_work_item(tmp_path):
    """Running the repair tool does not buy a clean scan — it causes the finding."""
    root = _control_root(tmp_path)
    _seed(root, "wi-backfilled", stamp="reconciled")

    violations = scan_work_item_provenance(control_root=root)

    assert len(violations) == 1
    assert "reconciled provenance" in violations[0].detail


@pytest.mark.coder
def test_scan_is_clean_for_a_sanctioned_work_item(tmp_path):
    """The negative control: the scanner is not simply reporting everything."""
    root = _control_root(tmp_path)
    _seed(root, "wi-authored", stamp="authored")

    assert scan_work_item_provenance(control_root=root) == []


# --------------------------------------------------------------------------- #
# The validator FAILS CLOSED
# --------------------------------------------------------------------------- #
@pytest.mark.coder
def test_unreachable_control_root_raises_rather_than_scanning_clean(tmp_path):
    """No Control Root is an inability to look, and must not read as a pass."""
    nowhere = tmp_path / "no" / "control" / "root"
    nowhere.mkdir(parents=True)

    with pytest.raises(provenance.ProvenanceStoreUnreadable):
        scan_work_item_provenance(control_root=nowhere)


@pytest.mark.coder
def test_unopenable_store_raises_rather_than_scanning_clean(tmp_path):
    """A store path that cannot be opened as a database fails the run."""
    root = _control_root(tmp_path)
    # Occupy the store path with a directory: nothing can open it as SQLite.
    (root / ".atdd" / "state" / "state.sqlite").mkdir(parents=True)

    with pytest.raises(provenance.ProvenanceStoreUnreadable):
        scan_work_item_provenance(control_root=root)


@pytest.mark.coder
def test_scan_spawns_no_provider_cli(tmp_path, monkeypatch):
    """Agnosticity guard (GT-004): core reads its own store, never a provider.

    Asserted on the *mechanism* rather than on an import list, because a lazy
    import inside a function launders a static import check.

    The assertion is an ALLOWLIST of one executable — ``git`` — mirroring the
    rule it guards. Git is VCS plumbing the Control Root resolver legitimately
    uses to find the worktree root; it is not a provider and answers nothing
    about the work item. Anything else spawned (``gh``, ``glab``, ``jira``, or
    whatever comes next) means the audit's answer depends on a provider being
    reachable, which is exactly the coupling this design exists to avoid.
    """
    import subprocess

    spawned: list[str] = []
    real_popen = subprocess.Popen

    # Popen is the single chokepoint every spawn helper (run, check_output,
    # check_call) funnels through, so recording there catches all of them
    # without double-counting or breaking run()'s internals.
    class _RecordingPopen(real_popen):
        def __init__(self, cmd, *args, **kwargs):
            exe = cmd[0] if isinstance(cmd, (list, tuple)) and cmd else str(cmd)
            spawned.append(str(exe))
            super().__init__(cmd, *args, **kwargs)

    monkeypatch.setattr(subprocess, "Popen", _RecordingPopen)

    root = _control_root(tmp_path)
    _seed(root, "wi-authored", stamp="authored")
    spawned.clear()  # seeding is test setup, not the audit

    assert scan_work_item_provenance(control_root=root) == []

    # Guard the guard. ``set(spawned) <= {"git"}`` is satisfied by an EMPTY list,
    # so if the recorder were mis-wired this assertion would pass forever while
    # observing nothing — the exact toothless shape the rule itself is written to
    # avoid. Proving the recorder saw the resolver's git call proves it was live.
    assert spawned, "spawn recorder observed nothing — the guard is not wired"
    assert set(spawned) <= {"git"}, f"provenance scan spawned a provider CLI: {spawned}"
