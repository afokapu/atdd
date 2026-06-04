# URN: test:govern-lifecycle:agent-behavior-rules-enforcement:E014-UNIT-004-runtime-default-command-derives-permission-policy-from-spec
# Acceptance: acc:govern-lifecycle:E014-UNIT-004-runtime-default-command-derives-permission-policy-from-spec
# WMBT: wmbt:govern-lifecycle:E014
# Phase: GREEN
"""acc:govern-lifecycle:E014-UNIT-004 — runtime cli-return launch transport derives
the permission policy from the DispatchSpec and never emits the forbidden flag.

#969 RED→GREEN: ShimAgentController._default_command must derive its permission
configuration from the launch-permission-policy carried on the DispatchSpec
(permission_mode + allowed_tools) — NOT from the E014-forbidden
``--dangerously-skip-permissions`` flag.

This is the cli-return / Shim launch transport reconciled to the SAME policy the
cmux-surface adapter (coach/commands/spawn.py::_claude_code_adapter) uses, so a
Shim-launched worker surfaces escalation-worthy decisions (a PermissionRequest
fires for any tool NOT in the scoped allowlist) exactly like the cmux path.
"""
from __future__ import annotations

import shlex

from atdd.runtime.agent_control import ShimAgentController


def test_default_command_never_emits_forbidden_flag(make_spec):
    """The forbidden flag must never appear, regardless of permission mode."""
    controller = ShimAgentController()
    for mode in ("acceptEdits", "default", "plan"):
        cmd = controller._default_command(make_spec(permission_mode=mode))
        assert "--dangerously-skip-permissions" not in cmd, (
            f"_default_command emitted the E014-forbidden flag for mode {mode!r}: {cmd!r}"
        )


def test_default_command_derives_permission_mode_from_spec(make_spec):
    """`--permission-mode <mode>` is taken verbatim from spec.permission_mode."""
    controller = ShimAgentController()
    cmd = controller._default_command(make_spec(permission_mode="acceptEdits"))
    assert "--permission-mode" in cmd, cmd
    assert cmd[cmd.index("--permission-mode") + 1] == "acceptEdits", cmd


def test_default_command_derives_allowed_tools_from_spec(make_spec):
    """`--allowedTools` carries the scoped allowlist from spec.allowed_tools.

    The allowlist is the leash that makes decisions surface: any tool NOT listed
    triggers a PermissionRequest instead of being silently auto-approved.
    """
    controller = ShimAgentController()
    tools = ("Bash", "Edit", "Read")
    cmd = controller._default_command(make_spec(allowed_tools=tools))
    assert "--allowedTools" in cmd, cmd
    assert cmd[cmd.index("--allowedTools") + 1] == "Bash Edit Read", cmd


def test_default_command_matches_cmux_adapter_shape(make_spec):
    """Parity with coach/commands/spawn.py::_claude_code_adapter — same
    permission-mode + space-joined scoped allowedTools string. One policy."""
    controller = ShimAgentController()
    spec = make_spec(
        permission_mode="acceptEdits",
        allowed_tools=(
            "Bash", "Edit", "Write", "Read", "TodoWrite", "Glob", "Grep", "WebFetch",
        ),
    )
    cmd = controller._default_command(spec)
    rendered = shlex.join(cmd)
    assert rendered == (
        'claude --permission-mode acceptEdits '
        '--allowedTools '
        + shlex.quote("Bash Edit Write Read TodoWrite Glob Grep WebFetch")
    ), rendered


def test_default_command_omits_allowed_tools_when_empty(make_spec):
    """An empty allowlist must not emit a dangling/empty --allowedTools arg."""
    controller = ShimAgentController()
    cmd = controller._default_command(make_spec(allowed_tools=()))
    assert "--allowedTools" not in cmd, cmd
