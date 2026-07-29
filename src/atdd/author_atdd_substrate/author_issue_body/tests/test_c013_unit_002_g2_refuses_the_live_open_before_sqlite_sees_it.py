# URN: test:author-atdd-substrate:author-issue-body:C013-UNIT-002-g2-refuses-the-live-open-before-sqlite-sees-it
# Acceptance: acc:author-atdd-substrate:C013-UNIT-002-g2-refuses-the-live-open-before-sqlite-sees-it
# WMBT: wmbt:author-atdd-substrate:C013
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""C013-UNIT-002 — G2 refuses the protected open BEFORE sqlite performs it.

Two things have to be true, and only the pair is worth anything:

1. The trap raises :class:`LiveStoreAccessError` on the protected path.
2. The real ``sqlite3.connect`` never ran.

(1) alone would be satisfied by a guard that raises *after* letting the open
through — which is a report, not a guard. The spy for (2) is the filesystem
itself: ``sqlite3.connect`` CREATES a missing database file, so a decoy path
that still does not exist afterwards is direct evidence the real call never
happened. No mock to mis-wire.

Selectivity is asserted in the same inner session: a DIFFERENT tmp path opens
normally and its file appears. A trap that simply broke all sqlite access would
also "pass" (1) and (2), and would be useless.

Proven INDEPENDENTLY of G1 and G3, and never aimed at production: the guard is
fault-injected onto a decoy under ``tmp_path`` via ``GUARD_TARGET_ENV``.
"""
from __future__ import annotations

import sqlite3

import pytest

from atdd.state.live_store_guard import (
    LiveStoreAccessError,
    assert_not_live_store,
    is_live_store,
)

from ._guard_probe_helpers import PLUGIN, inner_env, write_inner_conftest

_PROBE = '''
import os
import sqlite3
from pathlib import Path

import pytest

from atdd.state.live_store_guard import LiveStoreAccessError

DECOY = Path(os.environ["ATDD_LIVE_STORE_GUARD_TARGET"])
INNOCENT = DECOY.with_name("innocent.sqlite")


def test_the_protected_open_is_refused_and_never_reaches_sqlite():
    assert not DECOY.exists(), "precondition: the decoy must not exist yet"

    with pytest.raises(LiveStoreAccessError) as excinfo:
        sqlite3.connect(str(DECOY))

    # The refusal names the offending test, so a developer can find it.
    assert "test_the_protected_open_is_refused_and_never_reaches_sqlite" in str(excinfo.value)
    # sqlite3.connect CREATES a missing file. Its continued absence IS the spy:
    # the real connect never ran.
    assert not DECOY.exists(), "the real sqlite3.connect ran — the guard reported instead of preventing"


def test_the_trap_is_selective_not_a_blanket_sqlite_ban():
    conn = sqlite3.connect(str(INNOCENT))
    conn.execute("CREATE TABLE t (x)")
    conn.commit()
    conn.close()
    assert INNOCENT.exists(), "an unprotected path must open normally"
'''


@pytest.mark.coder
def test_c013_unit_002_g2_refuses_the_live_open_before_sqlite_sees_it(
    pytester, tmp_path, monkeypatch
):
    decoy = tmp_path / "decoy-store.sqlite"

    # --- the predicate, in-process: it recognises the protected path ---------
    protected = frozenset({decoy})
    assert is_live_store(decoy, protected)
    assert is_live_store(f"file:{decoy}?mode=ro", protected), (
        "a URI-form open must not walk around the guard"
    )
    assert not is_live_store(":memory:", protected)
    assert not is_live_store(tmp_path / "somewhere-else.sqlite", protected)

    with pytest.raises(LiveStoreAccessError):
        assert_not_live_store(decoy, protected, nodeid="probe::nodeid")
    # The negative control: an unprotected path is waved through.
    assert_not_live_store(tmp_path / "elsewhere.sqlite", protected, nodeid="probe::nodeid")

    # --- the wired fixture, in a real child session --------------------------
    write_inner_conftest(pytester)
    pytester.makepyfile(test_probe=_PROBE)
    inner_env(monkeypatch, control_root=None, guard_target=decoy)

    result = pytester.runpytest_subprocess("-p", PLUGIN, "-q")
    result.assert_outcomes(passed=2)

    # The child refused every protected open, so the decoy was never created.
    assert not decoy.exists(), "the inner session opened the protected store after all"
