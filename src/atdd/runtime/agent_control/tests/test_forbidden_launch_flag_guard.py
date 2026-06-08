# URN: test:govern-lifecycle:agent-behavior-rules-enforcement:E014-UNIT-005-runtime-launch-boundary-rejects-forbidden-flag
# Acceptance: acc:govern-lifecycle:E014-UNIT-005-runtime-launch-boundary-rejects-forbidden-flag
# WMBT: wmbt:govern-lifecycle:E014
# Phase: GREEN
"""acc:govern-lifecycle:E014-UNIT-005 — runtime launch boundary rejects the forbidden
flag in any launch argv (default-built or caller-injected).

#969 RED→GREEN: close the E014 enforcement gap in the runtime launch transport.

The coach-side guard (coach/commands/spawn.py::_assert_no_forbidden_flags) only
inspects the cmux adapter *command string*. The cli-return / Shim launch path
builds its own argv list (``_default_command`` / a caller-supplied
``agent_command``) that never passed through any guard — which is exactly why
the contradictory ``--dangerously-skip-permissions`` config survived here.

This module pins a runtime-local, import-clean (§3.3 stdlib-only) forbidden-flag
guard that EVERY launch path runs its argv through.
"""
from __future__ import annotations

import pytest

from atdd.runtime.agent_control import (
    ForbiddenLaunchFlagError,
    assert_no_forbidden_launch_flags,
)


def test_guard_rejects_bare_forbidden_flag():
    with pytest.raises(ForbiddenLaunchFlagError):
        assert_no_forbidden_launch_flags(["claude", "--dangerously-skip-permissions"])


def test_guard_rejects_equals_form_forbidden_flag():
    with pytest.raises(ForbiddenLaunchFlagError):
        assert_no_forbidden_launch_flags(
            ["claude", "--dangerously-skip-permissions=true"]
        )


def test_guard_allows_clean_policy_argv():
    # The sanctioned freedom set must pass the guard unharmed.
    assert_no_forbidden_launch_flags(
        ["claude", "--permission-mode", "acceptEdits", "--allowedTools", "Bash Edit"]
    )


# The launch-boundary integration of this guard (a forbidden flag refused before
# a worker is launched) is now exercised on the sole cmux-native launch path in
# test_e043_unit_001_cmux_native_launch_seed.py; the retired pty-shim controller
# spawn/default-command coverage was retired with the shim in #979.
