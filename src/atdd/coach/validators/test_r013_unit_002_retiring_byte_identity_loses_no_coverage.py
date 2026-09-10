# URN: test:govern-lifecycle:govern-lifecycle:R013-UNIT-002
# Acceptance: acc:govern-lifecycle:R013-UNIT-002-retiring-the-byte-identity-rule-loses-no-coverage
# WMBT: wmbt:govern-lifecycle:R013
# Phase: RED
# Layer: backend.unit
# Assertion: behavioral

"""R013-UNIT-002 — the byte-identity rule goes, and nothing else goes with it.

The two assertions being retired sit inside modules that do real work.
`test_worktree_enforcement.py` also proves the hooks block on main and honour the
CI bypass; `test_prepush_repo_validate_opt_in.py` also proves the expensive
repo-wide traversal stays behind its opt-in flag. Deleting a neighbour by accident
is how a migration removes enforcement while looking like tidying.

What makes the retirement safe is that every surviving check reads the TEMPLATE —
the hook logic itself — and only the two retired ones read the installed file. So
the migration changes where a hook lives, not what any surviving test can see.
That property is asserted here rather than assumed, because it is the whole
argument for the deletion.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

import atdd

pytestmark = [pytest.mark.coach, pytest.mark.platform]

_VALIDATORS = Path(atdd.__file__).resolve().parent / "coach" / "validators"
_MODULES = ("test_worktree_enforcement.py", "test_prepush_repo_validate_opt_in.py")

_RETIRED = {
    "test_installed_hooks_match_templates",
    "test_template_and_installed_hook_are_byte_identical",
}


def _tests_in(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {
        n.name
        for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")
    }


def test_r013_unit_002_the_byte_identity_assertions_are_gone():
    survivors = set()
    for name in _MODULES:
        survivors |= _tests_in(_VALIDATORS / name)
    still_there = sorted(_RETIRED & survivors)
    assert still_there == [], (
        f"these assertions still require an installed hook to be a byte-identical "
        f"copy of its template: {still_there}. They encode the model this "
        "migration retires, and leaving them is what makes the repo assert both."
    )


def test_r013_unit_002_the_surviving_checks_still_exist():
    """The neighbours must survive the deletion — named, not counted."""
    expected = {
        "test_worktree_enforcement.py": {
            "test_pre_commit_blocks_all_on_main",
            "test_pre_commit_has_ci_bypass",
            "test_pre_push_blocks_all_on_main",
            "test_pre_push_has_ci_bypass",
            "test_pre_merge_commit_blocks_on_main",
            "test_pre_merge_commit_has_ci_bypass",
        },
        "test_prepush_repo_validate_opt_in.py": {
            "test_full_repo_validate_is_gated_behind_opt_in_flag",
            "test_opt_in_flag_is_not_a_bypass_flag",
            "test_default_plan_push_does_not_run_full_repo_validate",
            "test_opt_in_runs_full_repo_validate",
        },
    }
    for name, wanted in expected.items():
        present = _tests_in(_VALIDATORS / name)
        missing = sorted(wanted - present)
        assert missing == [], (
            f"{name} lost checks the migration had no business touching: {missing}"
        )


def test_r013_unit_002_no_surviving_check_reads_an_installed_hook():
    """The argument for the deletion, asserted: survivors read templates only."""
    offenders = []
    for name in _MODULES:
        src = (_VALIDATORS / name).read_text(encoding="utf-8")
        for lineno, line in enumerate(src.splitlines(), 1):
            if "_INSTALLED_DIR" in line or "INSTALLED_HOOK" in line:
                offenders.append(f"{name}:{lineno}: {line.strip()}")
    assert offenders == [], (
        "a surviving check still reads the INSTALLED hook rather than the "
        "template, so it depends on the retired model:\n  " + "\n  ".join(offenders)
    )
