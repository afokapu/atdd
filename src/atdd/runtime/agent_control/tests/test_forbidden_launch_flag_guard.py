# URN: acc:govern-lifecycle:E014-UNIT-005-runtime-launch-boundary-rejects-forbidden-flag
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
    ShimAgentController,
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


def test_default_command_argv_passes_its_own_guard(make_spec):
    """The default command the controller builds is self-consistent with the guard."""
    controller = ShimAgentController()
    cmd = controller._default_command(make_spec(permission_mode="acceptEdits"))
    # Must not raise.
    assert_no_forbidden_launch_flags(cmd)


def test_spawn_rejects_caller_command_with_forbidden_flag(make_spec):
    """A caller-injected agent_command carrying the forbidden flag is refused at
    the launch boundary — the gap that let the contradiction slip through."""
    controller = ShimAgentController()
    with pytest.raises(ForbiddenLaunchFlagError):
        controller.spawn(
            make_spec(),
            agent_command=["claude", "--dangerously-skip-permissions"],
        )
