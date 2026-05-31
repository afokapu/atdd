# URN: component:govern-lifecycle:enforcement-substrate:test_api_validators_marked_github_api:backend:domain
# Runtime: python
# Purpose: Any coach validator that consumes a live-GitHub-API fixture MUST be marked
#          `github_api`, so the offline `--skip-api` pre-push gate deterministically skips it (#932).
"""
Meta-validator: GitHub-API-dependent validators must be ``github_api``-marked.

The pre-push hook runs ``atdd validate coach --local --skip-api`` to stay
**offline and diff-scoped** — ``--skip-api`` maps to ``-m "not github_api"``.
A validator that consumes a fixture backed by the live GitHub API
(``github_issues``, ``github_project_items``, …, all rooted at the
``_github_prefetch`` / ``github_client`` fixtures in
``coach/validators/conftest.py``) but is NOT marked ``github_api`` cannot be
deselected by ``--skip-api``. It then runs in the offline gate and:

  * fails on repo-wide issue-hygiene debt unrelated to the diff being pushed,
  * or (when the API is rate-limited / unreachable) skips non-deterministically,
  * or errors under ``-n auto`` when the shared session fixture fails across
    xdist workers.

This was the dominant reason every push needed ``atdd emergency`` (#928 /
#932). This meta-validator makes the marking contract enforceable: it
discovers the API-fixture set from conftest and fails if any validator test
uses one without a ``github_api`` mark (module-level ``pytestmark`` or a
function decorator).
"""
from __future__ import annotations

import ast
from pathlib import Path
from typing import Dict, List, Set

import pytest

import atdd

pytestmark = [pytest.mark.coach]


_VALIDATORS_DIR = Path(atdd.__file__).resolve().parent / "coach" / "validators"
_CONFTEST = _VALIDATORS_DIR / "conftest.py"

# Seed fixtures that directly touch the live GitHub API. Every fixture that
# (transitively) depends on one of these is API-backed too.
_API_SEED_FIXTURES = frozenset({"github_client", "_github_prefetch"})


def _is_pytest_fixture(node: ast.FunctionDef) -> bool:
    for dec in node.decorator_list:
        target = dec.func if isinstance(dec, ast.Call) else dec
        # @pytest.fixture / @fixture / @pytest.fixture(scope=...)
        if isinstance(target, ast.Attribute) and target.attr == "fixture":
            return True
        if isinstance(target, ast.Name) and target.id == "fixture":
            return True
    return False


def _discover_api_fixtures(conftest: Path) -> Set[str]:
    """Return every fixture name that transitively depends on a live-API seed."""
    if not conftest.is_file():
        return set(_API_SEED_FIXTURES)
    tree = ast.parse(conftest.read_text(encoding="utf-8"))
    fixture_params: Dict[str, List[str]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and _is_pytest_fixture(node):
            fixture_params[node.name] = [a.arg for a in node.args.args]

    api: Set[str] = set(_API_SEED_FIXTURES)
    changed = True
    while changed:
        changed = False
        for name, params in fixture_params.items():
            if name not in api and any(p in api for p in params):
                api.add(name)
                changed = True
    return api


def _mark_names_from_marklist(value: ast.AST) -> Set[str]:
    """Extract pytest.mark.<name> identifiers from a pytestmark value/list."""
    names: Set[str] = set()
    items = value.elts if isinstance(value, (ast.List, ast.Tuple)) else [value]
    for item in items:
        # pytest.mark.<name> or pytest.mark.<name>(...)
        target = item.func if isinstance(item, ast.Call) else item
        if isinstance(target, ast.Attribute):
            names.add(target.attr)
    return names


def _module_mark_names(tree: ast.Module) -> Set[str]:
    names: Set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id == "pytestmark":
                    names |= _mark_names_from_marklist(node.value)
    return names


def _decorator_mark_names(node: ast.FunctionDef) -> Set[str]:
    names: Set[str] = set()
    for dec in node.decorator_list:
        target = dec.func if isinstance(dec, ast.Call) else dec
        if isinstance(target, ast.Attribute):
            names.add(target.attr)
    return names


def _validator_files() -> List[Path]:
    files = sorted(_VALIDATORS_DIR.glob("test_*.py"))
    tests_subdir = _VALIDATORS_DIR / "tests"
    if tests_subdir.is_dir():
        files += sorted(tests_subdir.glob("test_*.py"))
    return files


def find_mismarked_api_validators() -> List[str]:
    """Return ``file:line — test`` for every API-fixture test missing github_api."""
    api_fixtures = _discover_api_fixtures(_CONFTEST)
    violations: List[str] = []
    for path in _validator_files():
        if path.name == Path(__file__).name:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError):
            continue
        module_marks = _module_mark_names(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            if not node.name.startswith("test_"):
                continue
            params = {a.arg for a in node.args.args}
            used_api = params & api_fixtures
            if not used_api:
                continue
            marks = module_marks | _decorator_mark_names(node)
            if "github_api" not in marks:
                rel = path.relative_to(_VALIDATORS_DIR.parent.parent.parent)
                violations.append(
                    f"{rel}:{node.lineno} — {node.name} uses API fixture(s) "
                    f"{sorted(used_api)} but is not marked github_api"
                )
    return violations


def test_api_dependent_validators_are_marked_github_api():
    """Every validator consuming a live-GitHub-API fixture must be github_api-marked.

    Otherwise ``atdd validate --skip-api`` (the offline pre-push gate) cannot
    deselect it, and it fails/errors on repo-wide state unrelated to the diff.
    """
    violations = find_mismarked_api_validators()
    assert not violations, (
        "API-dependent validators missing the `github_api` mark "
        f"({len(violations)}):\n\n  - "
        + "\n  - ".join(violations)
        + "\n\nAdd `github_api` to the module `pytestmark` (or as a function "
        "decorator). The offline `--skip-api` pre-push gate must be able to "
        "skip these — repo-wide GitHub state belongs in CI, not a diff-scoped "
        "push gate. See #932."
    )
