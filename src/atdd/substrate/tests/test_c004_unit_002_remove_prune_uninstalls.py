# URN: test:admit-substrate:substrate-admission:C004-UNIT-002-remove-prune-uninstalls
# Acceptance: acc:admit-substrate:C004-UNIT-002-remove-prune-uninstalls
# WMBT: wmbt:admit-substrate:C004
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""C004-UNIT-002 — an uninstall must actually uninstall (#1488).

`remove --prune` used to edit `substrate.lock.yaml` and nothing else: the package
stayed on disk, its rules stayed bound, and the command printed `removed <ref>` and
exited 0. The defect is not only the missing `rm` — it is that the command REPORTED
SUCCESS IT DID NOT ACHIEVE.

So these pin the three things the report claims: the directory is gone, the rules
are unbound, and a removal that removes nothing says so instead of lying.
"""
from __future__ import annotations

from atdd.substrate import admission, installer
from atdd.substrate.tests.conftest import (
    DOOMED,
    DOOMED_RULE,
    KEEPER,
    KEEPER_RULE,
    WORKSPACE,
    bound_conventions,
    installed_ids,
)


def _home(project_root, package_id: str):
    return installer.install_path(project_root, "extension", package_id, "0.1.0")


def test_prune_deletes_the_installed_package_directory(bound_substrate) -> None:
    assert _home(bound_substrate, DOOMED).is_dir()  # precondition

    admission.remove(DOOMED, project_root=bound_substrate, prune=True)

    assert not _home(bound_substrate, DOOMED).exists()
    assert _home(bound_substrate, KEEPER).is_dir()  # untouched


def test_remove_unbinds_only_the_removed_packages_rules(bound_substrate) -> None:
    admission.remove(DOOMED, project_root=bound_substrate, prune=True)

    bound = {c["convention_id"] for c in bound_conventions(bound_substrate)}
    assert DOOMED_RULE not in bound
    assert KEEPER_RULE in bound


def test_remove_without_prune_still_unbinds(bound_substrate) -> None:
    """`--prune` governs the DISK; it does not govern coherence.

    Withdrawing a package from the substrate lock while leaving its rules bound is
    incoherent whether or not the operator asked to reclaim the directory, so the
    unbind is unconditional.
    """
    out = admission.remove(DOOMED, project_root=bound_substrate)

    assert DOOMED not in installed_ids(bound_substrate)
    assert DOOMED_RULE not in {c["convention_id"] for c in bound_conventions(bound_substrate)}
    assert DOOMED_RULE in out["unbound"]


def test_removing_an_absent_package_is_a_truthful_no_op(bound_substrate) -> None:
    """Idempotent: the second removal must not claim to have removed anything."""
    first = admission.remove(DOOMED, project_root=bound_substrate, prune=True)
    assert first["removed"] == DOOMED

    second = admission.remove(DOOMED, project_root=bound_substrate, prune=True)

    assert second["removed"] is None  # nothing was removed, and it says so
    assert KEEPER in installed_ids(bound_substrate)  # and it broke nothing
    assert WORKSPACE in installed_ids(bound_substrate)
