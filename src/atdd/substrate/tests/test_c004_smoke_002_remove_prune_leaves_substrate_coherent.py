# URN: test:admit-substrate:substrate-admission:C004-SMOKE-002-remove-prune-leaves-substrate-coherent
# Acceptance: acc:admit-substrate:C004-SMOKE-002-remove-prune-leaves-substrate-coherent
# WMBT: wmbt:admit-substrate:C004
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""C004-SMOKE-002 — `atdd substrate remove --prune` through the real CLI (#1488).

The operator's evidence is what the command PRINTS. `removed <ref>` while the
package sits on disk with its rules still bound is the actual defect, so this
drives the real subprocess and holds the printed claim to the filesystem.
"""
from __future__ import annotations

from atdd.substrate import installer
from atdd.substrate.tests.conftest import (
    DOOMED,
    DOOMED_RULE,
    KEEPER,
    KEEPER_RULE,
    bound_conventions,
    installed_ids,
)


def test_remove_prune_uninstalls_and_stays_coherent(bound_substrate, run_atdd) -> None:
    root = bound_substrate
    home = installer.install_path(root, "extension", DOOMED, "0.1.0")
    assert home.is_dir()

    result = run_atdd(["substrate", "remove", DOOMED, "--prune"], root)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "removed" in result.stdout
    # The claim must be true on disk and in BOTH locks.
    assert not home.exists()
    assert DOOMED not in installed_ids(root)
    assert DOOMED_RULE not in {c["convention_id"] for c in bound_conventions(root)}
    # ...and the surviving extension is untouched.
    assert KEEPER_RULE in {c["convention_id"] for c in bound_conventions(root)}

    rebind = run_atdd(["substrate", "bind"], root)
    assert rebind.returncode == 0, rebind.stdout + rebind.stderr


def test_removing_an_absent_package_does_not_print_a_false_removed(
    bound_substrate, run_atdd
) -> None:
    root = bound_substrate
    run_atdd(["substrate", "remove", DOOMED, "--prune"], root)

    again = run_atdd(["substrate", "remove", DOOMED, "--prune"], root)

    assert again.returncode == 0, again.stdout + again.stderr
    assert f"removed {DOOMED}" not in again.stdout  # it removed nothing; it must not say it did
    assert "nothing to remove" in again.stdout
