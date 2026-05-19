# URN: test:observe-and-correct:observer-runtime-and-rules:C002-UNIT-005-suppress-marker-clears-violation
# Acceptance: acc:observe-and-correct:C002-UNIT-005-suppress-marker-clears-violation
# WMBT: wmbt:observe-and-correct:C002
# Phase: GREEN
# Layer: integration
# Runtime: python
# Purpose: Flag SMOKE-phase tests that substitute a production collaborator (#704 Tier 1).

"""SMOKE collaborator-substitution validator (#704, Tier 1).

A test labelled ``# Phase: SMOKE`` must exercise the real subject. A test
that substitutes one of the subject's collaborators — by ``monkeypatch.setattr``
or by assigning a locally-defined function/lambda over an object attribute —
is a unit test wearing a SMOKE label: it passes CI while exercising nothing
real. The lived incident is the observer's ``collect_input`` substitution
(``obs.collect_input = _synthetic``), which let an unwired observer ship GREEN.

Hard constraint: a static validator CANNOT certify that a test exercises real
infrastructure (that is a runtime-behaviour property, undecidable from source —
Rice's theorem). This validator therefore does only the *decidable negative*
check — catch collaborator substitution. The positive side (does it touch real
infra) is the Tier 2 runtime gate, out of scope here.

Detection is two AST patterns, both decidable:
  1. ``monkeypatch.setattr(...)`` — collaborator stubbing. ``monkeypatch``
     environment methods (``setenv`` / ``delenv`` / ``chdir`` /
     ``syspath_prepend``) are legitimate smoke setup and are NOT flagged.
  2. assignment of a locally-``def``'d function or ``lambda`` over an object
     attribute (``obj.method = local_fn``). Data assignments
     (``self.path = tmp_path``) are not flagged — the RHS must resolve to a
     function/lambda defined in the same test module.

Scope (Tier 1): **Python only.** Backend smoke tests (``test_*.py`` carrying
``# Phase: SMOKE``) are covered wherever they live — ``src/**`` or a consumer
repo's ``e2e/be/**``. A consumer repo's *frontend* e2e smoke tests are
TypeScript (``*smoke*.spec.ts``); Tier 1 does NOT scan them — TS substitution
detection needs non-``ast`` machinery (``test_smoke_coverage.py`` already
catches TS *mock-imports* for e2e smoke). TypeScript smoke-fidelity is a #704
follow-up, not silently in scope.

Known limitations (all mitigated by the ``suppress-and-clean`` escape hatch;
the first two closed precisely by #704 Tier 2's acceptance-``boundary_kind``
trace):
  - a fake injected from an *imported* helper is not caught (RHS not local);
  - wiring a real handler into real infra under test
    (``real_server.on_request = my_handler``) matches pattern 2 and is a
    false positive — suppress it with an inline marker;
  - TypeScript smoke tests are out of Tier 1 scope (see Scope above).

Failures route through ``assert_disposition_satisfied`` under
``tester.smoke.no-collaborator-substitution`` (``suppress-and-clean``).
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import List, Optional

import pytest

from atdd.coach.utils.repo import find_repo_root
from atdd.coach.utils.rule_binding import bind_rule
from atdd.coach.validators._violation import Violation
from atdd.coach.utils.disposition_gate import assert_disposition_satisfied


pytestmark = [pytest.mark.tester]


_RULE = bind_rule("tester.smoke.no-collaborator-substitution")
_VALIDATOR_ID = (
    "test_smoke_no_collaborator_substitution::"
    "test_smoke_tests_do_not_substitute_collaborators"
)
_SEVERITY = 4

# monkeypatch methods that set up the *environment* (legitimate in a smoke
# test) rather than substituting a collaborator.
_MONKEYPATCH_ENV_METHODS = frozenset(
    {"setenv", "delenv", "chdir", "syspath_prepend"}
)

# Directory names pruned from the repo scan.
_SKIP_DIRS = frozenset(
    {".git", "__pycache__", "node_modules", ".venv", "venv", ".atdd", ".mypy_cache"}
)

_PHASE_SMOKE_MARKER = "# Phase: SMOKE"


# ---------------------------------------------------------------------------
# Detection (pure — unit-tested directly against source strings)
# ---------------------------------------------------------------------------


def detect_substitutions(source: str) -> List[tuple[int, str]]:
    """Return ``(lineno, detail)`` for each collaborator-substitution site.

    Pure function over a Python source string. A syntax error yields a single
    synthetic finding so an unparseable smoke test is surfaced, not silently
    skipped.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return [(getattr(exc, "lineno", 1) or 1, f"unparseable test file: {exc}")]

    # Names bound to a locally-defined function or lambda in this module.
    local_callables: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            local_callables.add(node.name)
        elif isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and isinstance(node.value, ast.Lambda):
                    local_callables.add(tgt.id)

    findings: List[tuple[int, str]] = []
    for node in ast.walk(tree):
        # Pattern 1: monkeypatch.<method>(...)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            fn = node.func
            if isinstance(fn.value, ast.Name) and fn.value.id == "monkeypatch":
                if fn.attr == "setattr":
                    findings.append(
                        (node.lineno, "monkeypatch.setattr(...) substitutes a collaborator")
                    )
                # other monkeypatch.* (env methods) are intentionally ignored

        # Pattern 2: obj.attr = <local def/lambda>
        if isinstance(node, ast.Assign):
            value = node.value
            rhs_is_local_fn = (
                isinstance(value, ast.Lambda)
                or (isinstance(value, ast.Name) and value.id in local_callables)
            )
            if rhs_is_local_fn:
                for tgt in node.targets:
                    if isinstance(tgt, ast.Attribute):
                        try:
                            target_repr = ast.unparse(tgt)
                        except Exception:  # pragma: no cover - defensive
                            target_repr = f"<attr>.{tgt.attr}"
                        rhs = (
                            "<lambda>"
                            if isinstance(value, ast.Lambda)
                            else value.id  # type: ignore[union-attr]
                        )
                        findings.append(
                            (
                                node.lineno,
                                f"{target_repr} = {rhs} substitutes a collaborator "
                                f"(local function/lambda assigned over an attribute)",
                            )
                        )

    findings.sort(key=lambda f: f[0])
    return findings


# ---------------------------------------------------------------------------
# Repo scan
# ---------------------------------------------------------------------------


def _iter_smoke_test_files(repo_root: Path):
    """Yield ``test_*.py`` files that carry the ``# Phase: SMOKE`` header."""
    for path in repo_root.rglob("test_*.py"):
        if any(part in _SKIP_DIRS for part in path.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if _PHASE_SMOKE_MARKER in text:
            yield path, text


def collect_violations(repo_root: Optional[Path] = None) -> List[Violation]:
    """Scan every ``# Phase: SMOKE`` test for collaborator substitution."""
    root = Path(repo_root).resolve() if repo_root is not None else find_repo_root()
    violations: List[Violation] = []
    for path, text in _iter_smoke_test_files(root):
        try:
            rel = str(path.relative_to(root))
        except ValueError:
            rel = str(path)
        for lineno, detail in detect_substitutions(text):
            violations.append(
                Violation(
                    rule_id="tester.smoke.no-collaborator-substitution",
                    severity=_SEVERITY,
                    location=f"{rel}:{lineno}",
                    detail=detail,
                )
            )
    return violations


# ---------------------------------------------------------------------------
# Validator (orchestration)
# ---------------------------------------------------------------------------


def test_smoke_tests_do_not_substitute_collaborators():
    """SMOKE tests must not substitute a production collaborator.

    Convention: smoke.convention.yaml > collaborator_substitution_rules
    Rule: tester.smoke.no-collaborator-substitution (suppress-and-clean)
    """
    violations = collect_violations()
    assert_disposition_satisfied(
        validator_id=_VALIDATOR_ID,
        violations=violations,
    )
