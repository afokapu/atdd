"""
Fault-injection coverage for the implementation-root-resolution detector.

URN: urn:atdd:test:coach:validators:implementation_root_resolution

A rule that cannot fail is a stub. `coach.graph.implementation-root-resolution`
was `documentation-only` for four minor versions and gated nothing while 57 core
modules drifted back to the shape it forbids. Flipping it to `strict` (#1476) is
only meaningful if the detector actually catches the hardcode, so these tests
plant the fault and assert it is caught — and, just as importantly, assert the
compliant shape is *not* flagged, because a detector that fires on the fix would
push the next author straight back to hardcoding.
"""

from __future__ import annotations

import pytest

from atdd.coach.validators.test_implementation_root_resolution import (
    find_hardcoded_stack_roots,
)


pytestmark = [pytest.mark.coach]


def _locations(source: str):
    return [v.location for v in find_hardcoded_stack_roots(source, "sample.py")]


def test_catches_repo_root_anchored_stack_path():
    """The canonical fault: a module-level constant freezing the python root."""
    source = 'REPO_ROOT = find_repo_root()\nPYTHON_DIR = REPO_ROOT / "python"\n'
    violations = find_hardcoded_stack_roots(source, "sample.py")

    assert len(violations) == 1
    assert violations[0].location == "sample.py:2"
    assert violations[0].rule_id == "coach.graph.implementation-root-resolution"
    assert "resolve_code_root" in violations[0].detail


@pytest.mark.parametrize(
    "expression",
    [
        'REPO_ROOT / "python"',
        'REPO_ROOT / "web" / "src"',
        'REPO_ROOT / "supabase" / "functions"',
        'REPO_ROOT / "web" / "tsconfig.json"',
        'find_repo_root() / "python" / "app.py"',
        'repo_root / "supabase" / "migrations"',
        'root / "typescript"',
    ],
)
def test_catches_every_anchored_stack_shape(expression):
    """Chained, called, and lowercase-anchored forms are all the same fault."""
    assert _locations(f"X = {expression}\n") == ["sample.py:1"]


def test_chained_path_is_reported_once_at_the_outermost_link():
    """`ROOT / "web" / "src"` is one site, not two.

    Counting the inner `ROOT / "web"` separately would double-report the site
    and misname the stack path the author actually wrote.
    """
    violations = find_hardcoded_stack_roots('X = REPO_ROOT / "web" / "src"\n', "s.py")

    assert len(violations) == 1
    assert "'web/src'" in violations[0].detail


def test_ignores_paths_anchored_at_a_resolved_root():
    """The compliant shape must not be flagged, or the fix looks like the fault."""
    source = (
        'PYTHON_ROOT = resolve_code_root("python", REPO_ROOT)\n'
        'TRAINS = PYTHON_ROOT / "trains"\n'
        'APP = PYTHON_ROOT / "app.py"\n'
    )
    assert find_hardcoded_stack_roots(source, "sample.py") == []


def test_ignores_repo_root_anchored_non_stack_paths():
    """Only *stack* roots are config-driven. plan/ and contracts/ are core's own."""
    source = (
        'PLAN_DIR = REPO_ROOT / "plan"\n'
        'CONTRACTS = REPO_ROOT / "contracts"\n'
        'E2E = REPO_ROOT / "e2e" / "conftest.py"\n'
    )
    assert find_hardcoded_stack_roots(source, "sample.py") == []


def test_ignores_stack_named_segment_that_is_not_the_anchor():
    """`SOME_DIR / "python"` is not a repo-root anchor and is none of our business."""
    source = 'X = CONTRACTS_DIR / "python"\n'
    assert find_hardcoded_stack_roots(source, "sample.py") == []
