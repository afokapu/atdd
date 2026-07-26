# URN: test:author-atdd-substrate:author-issue-body:C013-SMOKE-001-g3-catches-a-subprocess-write
# Acceptance: acc:author-atdd-substrate:C013-SMOKE-001-g3-catches-a-subprocess-write
# WMBT: wmbt:author-atdd-substrate:C013
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""C013-SMOKE-001 — G3 catches a store write that G2 structurally cannot see.

G2 patches ``sqlite3.connect`` in the pytest process. A child process has its own
interpreter and its own ``sqlite3``, so the patch does not exist there. This is
not a hypothetical hole: ``author_issue_body/tests/_helpers.run_cli`` and
``test_r006_smoke_001``'s ``_run_cli`` both spawn real ``python -m atdd``
children, and a child that inherits the parent's environment or cwd resolves the
Control Root straight to production (#1582).

Real all the way down, per #1298 — no mock stands in for the mechanism:
  * a REAL child pytest session (``runpytest_subprocess``),
  * running the SHIPPED plugin by name (``-p atdd.state.live_store_guard_plugin``),
  * whose inner test spawns a REAL grandchild process,
  * that performs a REAL sqlite write to a REAL migrated State Store.

Safety: the protected store is a decoy under ``tmp_path``, built by the real
``init_state_store`` so it has genuine schema and migrations. The guard is
fault-injected onto it with ``GUARD_TARGET_ENV``. Production is not a
participant — the acceptance is that a guard must be shown to fire, and showing
it must never require damaging the thing it protects.

Proven INDEPENDENTLY of G1 and G2: the inner test's own assertions all PASS, and
the session still fails. The failure can only have come from G3.
"""
from __future__ import annotations

import pytest

from atdd.state.db import init_state_store

from ._guard_probe_helpers import PLUGIN, inner_env, write_inner_conftest

_PROBE = '''
import os
import subprocess
import sys
from pathlib import Path

DECOY = Path(os.environ["ATDD_LIVE_STORE_GUARD_TARGET"])

# Idempotent: this runs twice (once guarded, once as the baseline arm) against
# the same decoy, and must mutate the store BOTH times.
_WRITER = (
    "import sqlite3, sys;"
    "c = sqlite3.connect(sys.argv[1]);"
    "c.execute('CREATE TABLE IF NOT EXISTS g3_fault_injection (x)');"
    "c.execute('INSERT INTO g3_fault_injection VALUES (1)');"
    "c.commit(); c.close()"
)


def test_a_subprocess_writes_to_the_protected_store():
    """This test PASSES on its own terms. G3 must fail it anyway."""
    before = DECOY.stat().st_size
    proc = subprocess.run(
        [sys.executable, "-c", _WRITER, str(DECOY)],
        capture_output=True, text=True,
    )
    # The grandchild really did write — otherwise the probe proves nothing.
    assert proc.returncode == 0, proc.stderr
    assert DECOY.stat().st_size >= before
'''


@pytest.mark.smoke
def test_c013_smoke_001_g3_catches_a_subprocess_write(pytester, tmp_path, monkeypatch):
    # A REAL migrated State Store, standing in for production.
    decoy = init_state_store(db_path=tmp_path / "decoy" / ".atdd" / "state" / "state.sqlite")
    assert decoy.is_file(), "the decoy store must be real, not a stub"

    write_inner_conftest(pytester)
    pytester.makepyfile(test_probe=_PROBE)
    inner_env(monkeypatch, control_root=None, guard_target=decoy)

    result = pytester.runpytest_subprocess("-p", PLUGIN, "-q")

    # The inner test's own assertions passed; the session still fails, and the
    # failure is G3's. Both the per-test backstop (an ERROR at teardown, which
    # names the culprit) and the session digest fire.
    assert result.ret != 0, "G3 did not fail the session over a real subprocess write"
    stdout = result.stdout.str()
    assert "MUTATED the live State Store" in stdout, stdout[-3000:]
    assert "test_a_subprocess_writes_to_the_protected_store" in stdout, (
        "G3 must NAME the test that let the write through"
    )
    assert "The live State Store CHANGED during this test session" in stdout, (
        "the session-scoped digest backstop must fire too"
    )

    # Guard the guard: with the plugin absent the same session passes clean.
    # Without this arm, a G3 that fired on everything would look identical.
    baseline = pytester.runpytest_subprocess("-q")
    baseline.assert_outcomes(passed=1)
