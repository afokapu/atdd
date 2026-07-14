# URN: test:admit-substrate:substrate-admission:C004-UNIT-003-binding-substrate-coherence
# Acceptance: acc:admit-substrate:C004-UNIT-003-binding-substrate-coherence
# WMBT: wmbt:admit-substrate:C004
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""C004-UNIT-003 — THE COHERENCE INVARIANT (#1488).

    No rule bound in `binding.lock.yaml` may reference a package that
    `substrate.lock.yaml` says is not installed.

The two locks are projections of ONE substrate: the binder derives the binding
plan FROM the substrate lock. So a rule still bound to a package the substrate
lock no longer carries is not a stale cache — it is a split brain. `atdd enforce`
reads `binding.lock.yaml`, and would happily run rules from a package the
substrate believes was uninstalled.

This invariant is worth more than the missing `rm`. It catches the entire class of
bug rather than the one instance, and it would have caught #1488 on its own.

The oracle below reads the two lock artifacts directly instead of calling the
production coherence helper, on purpose: an invariant that shares no code with the
implementation cannot be fooled by a bug in the implementation.
"""
from __future__ import annotations

from atdd.substrate import admission
from atdd.substrate.tests.conftest import (
    DOOMED,
    KEEPER,
    KEEPER_RULE,
    WORKSPACE,
    bound_conventions,
    installed_ids,
)


def incoherences(project_root) -> list[str]:
    """Every bound rule that references a package absent from the substrate lock.

    A bound rule that names NO owning package is a violation too: a binding that
    cannot be attributed to an installed package cannot be shown to satisfy the
    invariant, and fail-closed is the only safe reading for the artifact that
    decides what enforces the repo.
    """
    installed = installed_ids(project_root)
    faults: list[str] = []
    for entry in bound_conventions(project_root):
        rule = entry.get("convention_id", "<unknown>")
        package = entry.get("package_id")
        if not package:
            faults.append(f"{rule}: bound, but names no owning package_id")
            continue
        if package not in installed:
            faults.append(f"{rule}: bound to package {package!r}, absent from substrate.lock.yaml")
        workspace = entry.get("workspace_id")
        if workspace and workspace not in installed:
            faults.append(f"{rule}: bound to workspace {workspace!r}, absent from substrate.lock.yaml")
    return faults


def test_a_freshly_bound_substrate_is_coherent(bound_substrate) -> None:
    assert incoherences(bound_substrate) == []


def test_removing_an_extension_leaves_none_of_its_rules_bound(bound_substrate) -> None:
    """The reported case: the extension goes, its shared workspace stays.

    The surviving workspace is what makes this the hard case — a coherence check
    that only looked at `workspace_id` would still resolve, and would miss the
    eight orphaned rules entirely.
    """
    admission.remove(DOOMED, project_root=bound_substrate, prune=True)

    assert incoherences(bound_substrate) == []
    assert WORKSPACE in installed_ids(bound_substrate)  # still needed by KEEPER
    still_bound = {c["convention_id"] for c in bound_conventions(bound_substrate)}
    assert KEEPER_RULE in still_bound  # no collateral unbinding


def test_removing_the_last_extension_and_its_workspace_leaves_no_orphans(
    bound_substrate,
) -> None:
    """Emptying the substrate must empty the bindings — not strand 34 live rules."""
    admission.remove(DOOMED, project_root=bound_substrate, prune=True)
    admission.remove(KEEPER, project_root=bound_substrate, prune=True)

    assert incoherences(bound_substrate) == []
    assert bound_conventions(bound_substrate) == []
