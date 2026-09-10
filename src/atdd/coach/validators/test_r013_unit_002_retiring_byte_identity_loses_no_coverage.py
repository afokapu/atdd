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
_REPO_ROOT = Path(atdd.__file__).resolve().parents[2]
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


#: Tests that legitimately touch an installed hook: they build a throwaway repo,
#: or they assert a dispatcher IS one, or they check mere presence.
_MAY_READ_INSTALLED = {
    "test_e034_integration_001_init_installs_three.py",
    "test_e063_integration_001_hook_template_change_propagates.py",
    "test_e063_smoke_001_real_commit_runs_changed_packaged_hook.py",
    "test_C002_smoke_hooks_fire_via_git.py",
    "test_m001_smoke_001_head_change_reconcile.py",
    "test_m001_unit_002_bypassed_hook_leaves_detectable_stale_base.py",
    "test_r013_unit_001_every_installed_hook_is_a_dispatcher.py",
    "test_r013_smoke_001_migrated_hooks_still_gate_a_real_repository.py",
}


def _div_segments(node):
    """Constant string segments of a left-deep ``a / b / c`` path expression."""
    out = []
    while isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        if isinstance(node.right, ast.Constant) and isinstance(node.right.value, str):
            out.append(node.right.value)
        node = node.left
    return out


def _reads_installed_hook_content(tree):
    """Lines where this repo's ``.atdd/hooks`` path is built AND its content read.

    Reading CONTENT is the defect; checking presence is not. `test_i13_*` and
    GT-004 both assert an installed hook EXISTS — a dispatcher satisfies that,
    and flagging it would have forced a per-file allowlist, which is how a file
    cleared for a presence check silently reintroduces a content assertion. That
    exact hole let a negative control pass here before this was narrowed.

    AST, not text: a text scan flagged two docstrings and this file's own marker
    constant — the false-positive shape that made a strict rule unusable in #1865.
    """
    names = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        v = node.value
        built = (
            (isinstance(v, ast.BinOp)
             and ".atdd" in _div_segments(v) and "hooks" in _div_segments(v))
            or (isinstance(v, ast.Constant) and isinstance(v.value, str)
                and ".atdd/hooks" in v.value)
        )
        if built:
            names[target.id] = node.lineno

    hits = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr in ("read_text", "read_bytes")
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id in names):
            hits.append(names[node.func.value.id])
    return sorted(set(hits))


def test_r013_unit_002_no_test_anywhere_reads_installed_hook_content():
    """The sweep that should have been run first, kept as a test.

    Scoping this migration by grepping the two modules already known to hold
    byte-identity assertions missed three more — a third validator, and two tests
    reading the installed pre-push to assert what it DOES. A sixth surfaced only
    in CI, in `tests/incident_defenses/`, outside every tree that was searched.

    Three misses of one shape is not bad luck, it is the wrong method: the
    property was checked at the instances already known instead of across the
    repo. So it is asserted repo-wide here.
    """
    offenders = []
    for path in sorted(_REPO_ROOT.rglob("test_*.py")):
        if ".git" in path.parts or "fixtures" in path.parts:
            continue
        if path.name in _MAY_READ_INSTALLED or path.resolve() == Path(__file__).resolve():
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError):  # atdd:suppress(coder.logging.coach-silent-swallow)
            continue
        offenders.extend(
            f"{path.relative_to(_REPO_ROOT)}:{n}" for n in _reads_installed_hook_content(tree)
        )

    assert offenders == [], (
        "these tests READ the content of this repo's installed hooks, which are "
        "dispatchers carrying no logic since #1492 — assert on the TEMPLATE "
        "instead, or add the file to _MAY_READ_INSTALLED if it builds its own "
        "throwaway repo:\n  " + "\n  ".join(offenders)
    )
