"""Pytest plugin: keep the whole suite off the live State Store (#1582).

Three layers, because no single one of them covers the ground:

**G1 — environment neutralization (session, autouse).** Pops
``ATDD_CONTROL_ROOT`` for the duration of the session. This is the *fix*, not
merely a guard: resolver Rule 1 (:mod:`atdd.state.paths`) returns the env
override and never consults the ``start=`` argument, so an exported
``ATDD_CONTROL_ROOT`` silently redirects every ``init_state_store(start=tmp_path)``
in the suite to production. Removing it from the session environment makes all
~33 such call sites correct by construction — the class fixed at the class
level, rather than 33 hand-edits that the next new test would not inherit.
Tests that legitimately exercise the override (E004-SMOKE-001) set it themselves
via ``monkeypatch.setenv``, which still works and is restored per test.

**G2 — fail-loud path trap (function, autouse).** Wraps ``sqlite3.connect``,
which is the single in-process chokepoint every store open funnels through
(``atdd.state.db.connect`` does ``import sqlite3`` then ``sqlite3.connect(...)``).
Patching ``atdd.state.db.connect`` would NOT work: every test does
``from atdd.state.db import connect`` at import time, so the name is already
bound in the test module and a later patch of the source module misses it
entirely. The trap raises before the open, so it prevents the write instead of
reporting it afterwards.

**G3 — fingerprint backstop (function + session).** G2 is blind to
subprocesses, and several smokes spawn real ``python -m atdd`` children
(``author_issue_body/tests/_helpers.run_cli``, ``test_r006_smoke_001``'s
``_run_cli``). A child process opens its own ``sqlite3`` in its own interpreter
and never sees the parent's monkeypatch. So the store is fingerprinted around
every test — four ``stat`` calls, affordable per-test — and digested around the
session for the definitive byte answer.

Sanctioned readers
------------------
``@pytest.mark.live_store_read`` permits G2's open for the handful of tests that
deliberately audit the live corpus (``coder/validators/test_state_store_invariants.py``
scans the real store by design). The marker declares intent; G3 still runs for
those tests, so "I only read it" is *proved* rather than trusted.
"""
from __future__ import annotations

import os
import sqlite3

import pytest

from atdd.state import live_store_guard as guard

#: Marker that permits opening the live store read-only.
READ_MARKER = "live_store_read"

_UNSET = object()


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        f"{READ_MARKER}: this test deliberately reads the live State Store; the "
        "write guard permits the open and the fingerprint backstop still proves "
        "it wrote nothing (#1582)",
    )




# ---------------------------------------------------------------------------
# G1 — environment neutralization
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session", autouse=True)
def _hermetic_control_root_env():
    """Pop ``ATDD_CONTROL_ROOT`` for the session; restore it afterwards.

    Session-scoped and autouse so it is in force before the first store-touching
    test imports anything. Restoring on teardown keeps the operator's shell
    contract intact for whatever runs after pytest in the same process.
    """
    previous = os.environ.pop(guard.CONTROL_ROOT_ENV, _UNSET)
    try:
        yield
    finally:
        if previous is not _UNSET:
            os.environ[guard.CONTROL_ROOT_ENV] = previous


# ---------------------------------------------------------------------------
# G3 — the rolling logical baseline
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session", autouse=True)
def _live_store_baseline(_hermetic_control_root_env):
    """Hold the last known-good LOGICAL snapshot, and audit the whole session.

    The baseline is a rolling one. A test that changes the store gets reported
    once and then becomes the new baseline, so a single write does not re-fail
    every test that happens to run after it.

    Depends on G1 so the protected path is resolved with the session's final
    environment.
    """
    protected = guard.protected_store_paths()
    state = {"protected": protected, "contents": guard.store_contents(protected)}
    session_start = state["contents"]
    yield state
    final = guard.store_contents(protected)
    detail = guard.describe_contents_change(session_start, final)
    if detail:
        pytest.fail(
            "The live State Store's CONTENTS changed across this test session.\n"
            + detail
            + "\n\nSomething wrote to production. If no individual test was named "
            "by the per-test backstop, the writer was either a child process (a "
            "smoke spawning `python -m atdd`) or a CONCURRENT OPERATOR SESSION "
            "sharing this store — the uids above tell you which: test fixtures "
            "look like 'wi-authored' or 'drifted-record', real records like a "
            "defect slug (#1582).",
            pytrace=False,
        )


# ---------------------------------------------------------------------------
# G2 + G3 (per-test half) — the trap and the backstop
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _live_store_write_guard(request, _live_store_baseline):
    """Refuse in-process opens of the live store; audit it around the test.

    The two halves are one fixture because they answer the same question from
    opposite sides: G2 stops the open it can see, G3 catches the write it
    cannot. Either alone leaves a hole the incident actually used.

    Deliberately does NOT request the ``monkeypatch`` fixture, and patches
    ``sqlite3.connect`` by hand under ``try/finally`` instead. An autouse fixture
    that requests ``monkeypatch`` hoists that fixture's setup ahead of the
    conftest autouse guards, which inverts its TEARDOWN relative to them: a
    test's own ``monkeypatch.setattr(subprocess, "run", ...)`` would then still
    be in force while the #771 git-pollution guard shells out in teardown, and
    that guard errors through no fault of the test. Owning the patch here keeps
    this guard from perturbing fixtures it does not own.
    """
    protected = _live_store_baseline["protected"]
    if not protected:
        # No resolvable Control Root ⇒ no live store ⇒ nothing to pollute. This
        # is vacuous, not unchecked (consumer checkouts, CI before `atdd init`).
        yield
        return

    permitted = request.node.get_closest_marker(READ_MARKER) is not None
    real_connect = sqlite3.connect

    if not permitted:
        def _guarded_connect(database, *args, **kwargs):
            guard.assert_not_live_store(
                database, protected, nodeid=request.node.nodeid
            )
            return real_connect(database, *args, **kwargs)

        sqlite3.connect = _guarded_connect

    # Two stages, so the per-test cost stays at one stat call: the cheap stat
    # decides whether reading rows is worth it, and only a trip escalates to the
    # logical check that renders the verdict. The stat must NOT be the verdict --
    # sqlite rewrites the main database when a clean close checkpoints the WAL,
    # so an honest read-only audit shifts its size and mtime without touching a
    # single row. That false positive was observed, not theorized.
    before_fp = guard.store_fingerprint(protected)
    try:
        yield
    finally:
        if not permitted:
            sqlite3.connect = real_connect

    if guard.store_fingerprint(protected) == before_fp:
        return

    after_contents = guard.store_contents(protected)
    detail = guard.describe_contents_change(_live_store_baseline["contents"], after_contents)
    # Re-baseline either way: a change reported once must not re-fail every
    # later test in the session.
    _live_store_baseline["contents"] = after_contents
    if not detail:
        return  # page churn / WAL checkpoint -- no row moved, nothing polluted
    pytest.fail(
        f"Test {request.node.nodeid!r} MUTATED the live State Store.\n"
        + detail
        + "\n\nThe in-process trap did not catch it, so the write came from a "
        "child process this test spawned. Give the subprocess an "
        "ATDD_CONTROL_ROOT under tmp_path -- inheriting the parent's environment "
        "or cwd resolves it to production (#1582).",
        pytrace=False,
    )
