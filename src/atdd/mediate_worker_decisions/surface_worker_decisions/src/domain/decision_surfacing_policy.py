"""DecisionSurfacingPolicy — the pure rule for what a spawned worker surfaces (WMBT E008/C006).

A worker only publishes a blocking decision to the cmux Feed when its launch does
NOT pre-authorize that decision. This policy partitions the worker's tools into an
``auto_allow`` set (read/edit tools, kept frictionless for autonomy) and a
``surface`` set (action-class decisions — Bash, and the native AskUserQuestion /
ExitPlanMode — that must reach the wrapper's PermissionRequest hook). It is a pure
value object: it produces the VALUES that land on the existing
``atdd.runtime.agent_control.DispatchSpec`` fields (``permission_mode`` +
``allowed_tools``); it is NOT a new shared type the launch transports import (per
§3.3 agent_control consumes the values from the spec, not this module).

Danger classification is NOT done here — every Bash command surfaces and the
daemon's ``tool_input_safety``/``match_danger`` decides auto vs human_required.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

# The tool classes that MUST always surface (never be pre-authorized at launch).
# Bash is the action-class tool the daemon mediates; AskUserQuestion / ExitPlanMode
# are native decisions the wrapper surfaces when not skipped.
ACTION_CLASS_TOOLS = frozenset({"Bash"})

# permission-modes that suppress every PermissionRequest — forbidden by this policy.
BYPASS_PERMISSION_MODES = frozenset({"bypassPermissions"})

# launch flags this policy must never emit (they suppress all decision surfacing).
FORBIDDEN_FLAGS: Tuple[str, ...] = ("--dangerously-skip-permissions",)

# The default scoped auto-allow set: read/edit tools that carry no escalation value,
# kept frictionless for autonomy. Bash is deliberately ABSENT so every command
# surfaces to the Feed for daemon mediation. AskUserQuestion / ExitPlanMode are
# native decisions and are never in allowed_tools either.
_DEFAULT_AUTO_ALLOW: Tuple[str, ...] = (
    "Read", "Edit", "Write", "TodoWrite", "Glob", "Grep", "WebFetch",
)
_DEFAULT_PERMISSION_MODE = "acceptEdits"


class PolicyError(ValueError):
    """Raised when a policy would suppress decision surfacing (bypass mode or an
    action-class tool placed in the auto-allow set)."""


@dataclass(frozen=True)
class DecisionSurfacingPolicy:
    """Frozen partition of a worker's tools into auto-allowed vs surfaced.

    ``permission_mode`` is one of the DispatchSpec modes (never a bypass mode).
    ``auto_allow_tools`` becomes ``allowed_tools`` on the spec; ``surface_tools``
    documents the decisions deliberately left un-allowed (always includes Bash).
    """

    agent_kind: str
    permission_mode: str
    auto_allow_tools: Tuple[str, ...]
    surface_tools: Tuple[str, ...]


def validate_policy(policy: DecisionSurfacingPolicy) -> None:
    """Raise ``PolicyError`` if ``policy`` would suppress decision surfacing.

    A policy is invalid when it sets a bypass permission_mode or pre-authorizes any
    action-class tool (so the daemon could never mediate it). Pure check, reused by
    both the factory and the renderer so an invalid policy is never silently emitted.
    """
    if policy.permission_mode in BYPASS_PERMISSION_MODES:
        raise PolicyError(
            f"permission_mode {policy.permission_mode!r} suppresses every "
            f"PermissionRequest; decisions could never surface to the Feed"
        )
    leaked = ACTION_CLASS_TOOLS.intersection(policy.auto_allow_tools)
    if leaked:
        raise PolicyError(
            f"action-class tool(s) {sorted(leaked)} must never be auto-allowed; "
            f"they must surface to the Feed for daemon mediation"
        )


def make_policy(agent_kind: str) -> DecisionSurfacingPolicy:
    """Build the default decision-surfacing policy for ``agent_kind``.

    Returns acceptEdits + the scoped read/edit auto-allow set (Bash excluded). The
    result is validated so a surfacing-suppressing policy can never be constructed.
    """
    policy = DecisionSurfacingPolicy(
        agent_kind=agent_kind,
        permission_mode=_DEFAULT_PERMISSION_MODE,
        auto_allow_tools=_DEFAULT_AUTO_ALLOW,
        surface_tools=tuple(sorted(ACTION_CLASS_TOOLS)),
    )
    validate_policy(policy)
    return policy
