"""`atdd coach transition <N> <TO>` — the coach-archetype lifecycle transition verb.

C1 (#1304, child of umbrella #1303 "retire ``atdd issue``, split author/coach").
This module is the canonical HOME of the phase-transition orchestration that used
to be reached only via ``atdd issue <N> --status <TO>``. The orchestration was
MOVED here (not duplicated): the shared store/manifest/github write helpers stay
on :class:`~atdd.coach.commands.issue.IssueManager` and are imported, and the
gate/compliance/re-enter building blocks stay on
:class:`~atdd.coach.commands.issue_lifecycle.IssueLifecycle` and are reused.

Two public entry points:

- :func:`apply_transition` — the orchestration itself (gate → compliance →
  ``IssueManager.update`` → COMPLETE archive → re-enter). The gate it runs
  registers its own checks (#1619), so EVERY caller of this function gets the
  same checks consulted. The historical split — where the CLI verb enforced the
  operator token and the deprecated ``atdd update``/``atdd archive`` paths did
  not — is GONE, deliberately: it made enforcement a property of the caller
  rather than of the edge being crossed.
- :func:`run` — the ``atdd coach transition`` CLI entry. Parses ``<N> <TO>
  [--force]`` and calls ``apply_transition``. It no longer registers anything.

``IssueLifecycle.transition`` now delegates to :func:`apply_transition`, so its
existing callers (``atdd update``/``atdd archive`` shims, the #1020/#1017 gate
tests) keep working through the one moved implementation.

Convention: src/atdd/coach/conventions/issue.convention.yaml
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional


def apply_transition(
    issue_number: int,
    status: str,
    *,
    force: bool = False,
    target_dir: Optional[Path] = None,
) -> int:
    """Transition an issue to ``status``, then re-enter to show updated state.

    The full orchestration, moved verbatim from ``IssueLifecycle.transition``:

    1. ``_transition_gate`` — the #1020 enforcing per-transition chokepoint
       (fail-closed; the operator-approval check consults it when registered).
    2. ``_compliance_gate`` — PLANNED and beyond require a template-compliant
       issue body (``--force`` overrides).
    3. ``IssueManager.update`` — state-machine validation, train enforcement,
       COMPLETE gates, the sole authoritative github label swap, the store-first
       write (``_store_set_status``) and the manifest mirror
       (``_update_manifest_status`` with its strict/non-strict commit path).
    4. COMPLETE also auto-archives (close WMBTs + parent).
    5. Re-enter in display-only mode so a landed transition is never masked by a
       branch-creation layout error.

    The gate registers the checks it consults (#1619), so a programmatic caller
    is held to the same edges as the CLI verb. Returns 0 on success, non-zero on
    any gate/validation failure.
    """
    # Shared write helpers stay on IssueManager (store/manifest/github); the
    # gate/compliance/re-enter building blocks stay on IssueLifecycle. We import
    # both and orchestrate — no logic is duplicated here.
    from atdd.coach.commands.issue import IssueManager
    from atdd.coach.commands.issue_lifecycle import IssueLifecycle

    lifecycle = IssueLifecycle(target_dir)

    # Enforcing per-transition gate — the #1020 keystone. A failing registered
    # check returns non-zero here, so we never reach IssueManager.update()'s
    # label/phase swap. The gate registers its own checks (#1619), so this is
    # enforcing for every caller — not only for the CLI verb below.
    gate_rc = lifecycle._transition_gate(issue_number, status, force=force)
    if gate_rc != 0:
        return gate_rc

    # Template compliance gate — PLANNED and beyond require a fully populated
    # issue body (SPEC-COACH-ORCH-0011). --force overrides.
    if not force:
        gate_rc = lifecycle._compliance_gate(issue_number, status)
        if gate_rc != 0:
            return gate_rc

    manager = IssueManager(lifecycle.target_dir)
    issue_id = str(issue_number)

    rc = manager.update(
        issue_id=issue_id,
        status=status,
        force=force,
    )
    if rc != 0:
        return rc

    # COMPLETE auto-archives: close WMBTs + parent issue.
    if status.upper() == "COMPLETE":
        arc_rc = manager.archive(issue_id=issue_id)
        if arc_rc != 0:
            print(f"Warning: Archive step returned {arc_rc} after COMPLETE transition.")

    # R002: re-enter in display-only mode so the post-transition path does not
    # attempt to create a worktree branch (and therefore cannot fail on the
    # branch-creation layout check). The transition itself already landed.
    return lifecycle._reenter_display_only(issue_number)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="atdd coach transition",
        description=(
            "Transition an ATDD issue to a new lifecycle phase (the coach-"
            "archetype replacement for `atdd issue <N> --status <TO>`)."
        ),
    )
    parser.add_argument(
        "issue_number",
        type=int,
        help="GitHub issue number to transition.",
    )
    parser.add_argument(
        "status",
        type=str,
        metavar="TO",
        help="Target phase (INIT/PLANNED/RED/GREEN/SMOKE/REFACTOR/COMPLETE/BLOCKED).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Bypass gate/body checks (train assignment is still enforced).",
    )
    return parser


def run(argv: list[str]) -> int:
    """``atdd coach transition <N> <TO> [--force]`` — the canonical CLI entry.

    Parses and applies. It NO LONGER REGISTERS the gate checks (#1619).

    It used to, and that was the defect. Registration living at this verb dispatch
    made ``GATE_REGISTRY``'s contents depend on HOW a transition was invoked
    rather than on WHICH edge was being crossed, so every path that did not shell
    out to this verb — programmatic ``IssueLifecycle.transition``, the
    ``issue_reconcile_state`` replay, the ``resume.py`` walk, the watcher —
    evaluated an empty registry and proceeded.

    ``atdd.coach.gate.enforcement.enforce_transition_gate`` now performs the
    registration as part of deciding, so this verb gets exactly the checks it
    always did, by the same route as every other caller. Which transitions
    actually ENFORCE is still decided by ``.atdd/config.yaml`` ``gate.transitions``
    (default PLANNED->RED) — unchanged.
    """
    ns = _build_parser().parse_args(argv)
    return apply_transition(ns.issue_number, ns.status, force=ns.force)
