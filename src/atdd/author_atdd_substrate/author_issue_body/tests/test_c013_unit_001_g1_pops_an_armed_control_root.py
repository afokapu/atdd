# URN: test:author-atdd-substrate:author-issue-body:C013-UNIT-001-g1-pops-an-armed-control-root
# Acceptance: acc:author-atdd-substrate:C013-UNIT-001-g1-pops-an-armed-control-root
# WMBT: wmbt:author-atdd-substrate:C013
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""C013-UNIT-001 — G1 pops an armed ``ATDD_CONTROL_ROOT`` for the session.

G1 is the *fix*, not a detector. Resolver Rule 1 returns the env override and
never consults ``start=``, so an exported ``ATDD_CONTROL_ROOT`` redirects every
``init_state_store(start=tmp_path)`` in the suite to production (#1582). G1
removes it for the session, which makes ~33 such call sites correct by
construction.

Proven INDEPENDENTLY of G2 and G3: this probe never opens a store at all, so it
cannot pass on the strength of another layer. A real child pytest session runs
with the variable armed and the inner test reads ``os.environ``.

Guard the guard: the same inner test also runs WITHOUT the plugin and is
asserted to FAIL. Without that arm, a probe incapable of observing a non-popping
G1 would pass forever — the toothless shape #1582 exists to rule out.
"""
from __future__ import annotations

import pytest

from ._guard_probe_helpers import PLUGIN, inner_env, write_inner_conftest

_PROBE = """
import os

def test_control_root_is_absent_inside_the_session():
    observed = os.environ.get("ATDD_CONTROL_ROOT")
    assert observed is None, "G1 did not pop the armed override: " + repr(observed)
"""


@pytest.mark.coder
def test_c013_unit_001_g1_pops_an_armed_control_root(pytester, tmp_path, monkeypatch):
    armed = tmp_path / "armed-control-root"
    armed.mkdir()
    write_inner_conftest(pytester)
    pytester.makepyfile(test_probe=_PROBE)

    # Protect nothing in the inner session: this probe is about G1 alone, and
    # leaving G2/G3 to resolve a real path would let another layer's behaviour
    # colour the result.
    applied = inner_env(monkeypatch, control_root=armed, guard_target="")
    assert applied["ATDD_CONTROL_ROOT"] == str(armed), "the probe failed to arm the override"

    with_plugin = pytester.runpytest_subprocess("-p", PLUGIN, "-q")
    with_plugin.assert_outcomes(passed=1)

    # Guard the guard — with the plugin absent the override survives and the
    # probe FAILS, proving it can actually observe a non-popping G1.
    without_plugin = pytester.runpytest_subprocess("-q")
    without_plugin.assert_outcomes(failed=1)
