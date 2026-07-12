# URN: component:govern-lifecycle:enforcement-substrate:test_live_smoke_execution:backend:application
# Runtime: python
# Purpose: Issue #1151 — an execution_kind: live_smoke acceptance's anchored test must run-or-fail against real infrastructure; a self-skip lets it pass by never executing.

"""Live-smoke execution conformance validator (issue #1151).

Binds ``tester.acceptance-violation.live-smoke-acceptance-must-execute``.

The substrate emits a ``Violation`` from a test's *outcome*, but a
``pytest.skip()`` (or an env-gated ``live_smoke_available()`` self-skip) raises
nothing — so the acceptance's rule passes vacuously and a *skipped* live_smoke
test is indistinguishable from a *passing* one (#1076: C010-SMOKE-001 "passed"
by skipping; run for real it FAILED). Spec §11 assumes violations flow from test
*failure*; absence-of-execution is not modeled.

The deterministic, static guard this validator adds: an
``execution_kind: live_smoke`` acceptance's anchored test must NOT be able to
skip itself. A test that cannot self-skip must run-or-fail; combined with a
real-infrastructure workspace (the SMOKE run executes inside the workspace
provider), that is the live-execution guarantee. Completes the chain after
``tester.acceptance-violation.hermetic-live-smoke-required-must-have-paired-smoke-acceptance``
(pairing is required; this makes the paired live_smoke actually execute).

``evaluate_live_smoke_execution`` is a pure evaluator over
``(location, acceptance_urn, [(test_path, test_source), ...])`` entries.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

import pytest

from atdd.coach.utils.repo import find_repo_root
from atdd.coach.utils.rule_binding import bind_rule
from atdd.coach.validators._violation import Violation
from atdd.tester.validators._acceptance_walker import (
    acceptance_urn,
    assert_substrate_strict,
    iter_repo_acceptances,
    scan_test_acceptance_headers,
)


pytestmark = [pytest.mark.platform]


_RULE = bind_rule("tester.acceptance-violation.live-smoke-acceptance-must-execute")
_VALIDATOR_ID = (
    "test_live_smoke_execution::test_every_live_smoke_acceptance_executed"
)

_LIVE_SMOKE_KIND = "live_smoke"

# Self-skip mechanisms that let a live_smoke test "pass" by never executing.
_SELF_SKIP_PATTERNS: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"\bpytest\.skip\s*\("), "pytest.skip(...)"),
    (re.compile(r"\bpytest\.importorskip\s*\("), "pytest.importorskip(...)"),
    (re.compile(r"@\s*(?:pytest\.mark\.)?skipif\b"), "@pytest.mark.skipif"),
    (re.compile(r"@\s*(?:pytest\.mark\.)?skip\b"), "@pytest.mark.skip"),
    (re.compile(r"\bmark\.skipif?\s*\("), "pytest.mark.skip(if)(...)"),
    (
        re.compile(r"\blive_smoke_available\s*\("),
        "live_smoke_available() self-skip guard",
    ),
]


def detect_self_skip(source: str) -> Optional[str]:
    """Return a label for the first self-skip mechanism in *source*, else None."""
    for pattern, label in _SELF_SKIP_PATTERNS:
        if pattern.search(source):
            return label
    return None


def evaluate_live_smoke_execution(
    entries: Sequence[Tuple[str, str, Sequence[Tuple[str, str]]]],
) -> List[Violation]:
    """Return execution violations for live_smoke acceptances (pure).

    ``entries`` is a sequence of
    ``(location, acceptance_urn, [(test_path, test_source), ...])`` — one entry
    per ``execution_kind: live_smoke`` acceptance and its anchored test files.
    A ``Violation`` is emitted for each anchored test that can self-skip.
    """
    violations: List[Violation] = []
    for location, urn, tests in entries:
        for test_path, source in tests:
            mechanism = detect_self_skip(source)
            if mechanism is None:
                continue
            violations.append(
                Violation(
                    rule_id=_RULE.rule_id,
                    severity=_RULE.severity,
                    location=str(test_path),
                    detail=(
                        f"live_smoke acceptance {urn!r} is anchored to "
                        f"{test_path} which can self-skip ({mechanism}). A skipped "
                        f"live_smoke test passes vacuously — it never executes "
                        f"against real infrastructure. Remove the self-skip so it "
                        f"runs-or-fails (it must run inside the workspace provider)."
                    ),
                    fix_hint_ref=_RULE.fix_hint_ref,
                )
            )
    return violations


def collect_violations(repo_root: Optional[Path] = None) -> List[Violation]:
    """Walk plan/ for live_smoke acceptances and scan their anchored tests."""
    root = Path(repo_root).resolve() if repo_root is not None else find_repo_root()
    test_index = scan_test_acceptance_headers(root)

    entries: List[Tuple[str, str, List[Tuple[str, str]]]] = []
    for raw in iter_repo_acceptances(root):
        if raw.body.get("execution_kind") != _LIVE_SMOKE_KIND:
            continue
        urn = acceptance_urn(raw.body)
        if not urn:
            # Missing URN is policed by URN-graph validators; skip here.
            continue
        tests: List[Tuple[str, str]] = []
        for test_file in test_index.get(urn, []):
            try:
                tests.append((str(test_file), test_file.read_text(encoding="utf-8", errors="ignore")))
            except OSError:
                continue
        if tests:
            entries.append((raw.location, urn, tests))

    return evaluate_live_smoke_execution(entries)


def test_every_live_smoke_acceptance_executed() -> None:
    """Every live_smoke acceptance's anchored test runs-or-fails (cannot skip)."""
    assert_substrate_strict(_VALIDATOR_ID, collect_violations())


# --------------------------------------------------------------------------- #
# Constant-evidence detector (issue #1298 — extends #1151)                     #
#                                                                              #
# A live_smoke test that cannot self-skip still passes vacuously if the        #
# harness it invokes returns FIXED success-shaped evidence regardless of what  #
# happened (afokapu/atdd#1192: the Y002 smoke built the launch-argv string and #
# returned hardcoded {"surfaced": True}, 0.12s, no worker, yet was labelled    #
# "Live end-to-end"). This static guard flags a harness whose every return is  #
# an all-constant dict literal AND whose body has no assert/raise — it can     #
# never fail and proves nothing ran against real infrastructure.               #
# --------------------------------------------------------------------------- #
_CONST_RULE = bind_rule(
    "tester.acceptance-violation.live-smoke-evidence-must-not-be-constant"
)
_CONST_VALIDATOR_ID = (
    "test_live_smoke_execution::test_no_live_smoke_harness_returns_constant_evidence"
)

# The anchored test imports its harness from a module whose name carries this
# hint (e.g. ``…feed_daemon.live_smoke``); the harness function is then called.
_LIVE_SMOKE_MODULE_HINT = "live_smoke"


def _find_funcdef(tree: ast.AST, name: str) -> Optional[ast.FunctionDef]:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    return None


def _is_all_constant_dict(node: Optional[ast.AST]) -> bool:
    """True for a non-empty dict literal whose every value is a constant."""
    if not isinstance(node, ast.Dict):
        return False
    if not node.values:
        return False
    return all(isinstance(value, ast.Constant) for value in node.values)


def _func_can_fail(func: ast.FunctionDef) -> bool:
    """True if the function contains any assert or raise (so it can fail loudly)."""
    for node in ast.walk(func):
        if isinstance(node, (ast.Assert, ast.Raise)):
            return True
    return False


def detect_constant_evidence(harness_source: str, func_name: str) -> Optional[str]:
    """Return a theater label if ``func_name`` returns only constant evidence.

    A harness is flagged when EVERY non-None return is an all-constant dict
    literal AND the function body contains no assert/raise — it reports fixed
    success regardless of the real outcome and can never fail. Returns None for
    a harness that computes any evidence value or that can assert/raise, and for
    an unparseable source or a missing function.
    """
    try:
        tree = ast.parse(harness_source)
    except SyntaxError:
        return None
    func = _find_funcdef(tree, func_name)
    if func is None:
        return None
    returns = [
        node
        for node in ast.walk(func)
        if isinstance(node, ast.Return) and node.value is not None
    ]
    if not returns:
        return None
    if not all(_is_all_constant_dict(node.value) for node in returns):
        return None
    if _func_can_fail(func):
        return None
    return (
        f"harness {func_name!r} returns only constant dict evidence and contains "
        f"no assert/raise, so it cannot fail"
    )


def _harness_calls_in_test(test_source: str) -> List[Tuple[str, str]]:
    """Return ``[(module, func_name)]`` for harnesses imported from a *live_smoke*
    module and actually invoked in the test source."""
    try:
        tree = ast.parse(test_source)
    except SyntaxError:
        return []
    imported: dict = {}  # local_name -> (module, original_name)
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.ImportFrom)
            and node.module
            and _LIVE_SMOKE_MODULE_HINT in node.module
        ):
            for alias in node.names:
                imported[alias.asname or alias.name] = (node.module, alias.name)
    called: List[Tuple[str, str]] = []
    seen = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in imported
            and node.func.id not in seen
        ):
            seen.add(node.func.id)
            called.append(imported[node.func.id])
    return called


def _module_to_source_path(repo_root: Path, module: str) -> Path:
    return repo_root / "src" / Path(*module.split(".")).with_suffix(".py")


def evaluate_constant_evidence(
    entries: Sequence[Tuple[str, str, Sequence[Tuple[str, str, str]]]],
) -> List[Violation]:
    """Return constant-evidence violations for live_smoke harnesses (pure).

    ``entries`` is a sequence of
    ``(location, acceptance_urn, [(harness_path, func_name, harness_source), ...])``.
    A ``Violation`` is emitted for each harness that returns only constant evidence.
    """
    violations: List[Violation] = []
    for _location, urn, harnesses in entries:
        for harness_path, func_name, source in harnesses:
            label = detect_constant_evidence(source, func_name)
            if label is None:
                continue
            violations.append(
                Violation(
                    rule_id=_CONST_RULE.rule_id,
                    severity=_CONST_RULE.severity,
                    location=str(harness_path),
                    detail=(
                        f"live_smoke acceptance {urn!r} is anchored to a test that "
                        f"invokes {harness_path}::{func_name} — {label}. A harness "
                        f"that returns fixed success-shaped evidence and cannot fail "
                        f"is theater: it never proves anything ran against real "
                        f"infrastructure. Return values COMPUTED from the real "
                        f"outcome, or assert/raise on it."
                    ),
                    fix_hint_ref=_CONST_RULE.fix_hint_ref,
                )
            )
    return violations


def collect_constant_evidence_violations(
    repo_root: Optional[Path] = None,
) -> List[Violation]:
    """Walk live_smoke acceptances → anchored tests → invoked harnesses and flag
    any harness returning only constant evidence."""
    root = Path(repo_root).resolve() if repo_root is not None else find_repo_root()
    test_index = scan_test_acceptance_headers(root)

    entries: List[Tuple[str, str, List[Tuple[str, str, str]]]] = []
    for raw in iter_repo_acceptances(root):
        if raw.body.get("execution_kind") != _LIVE_SMOKE_KIND:
            continue
        urn = acceptance_urn(raw.body)
        if not urn:
            continue
        harnesses: List[Tuple[str, str, str]] = []
        for test_file in test_index.get(urn, []):
            try:
                test_src = test_file.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for module, func_name in _harness_calls_in_test(test_src):
                path = _module_to_source_path(root, module)
                try:
                    src = path.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue
                harnesses.append((str(path), func_name, src))
        if harnesses:
            entries.append((raw.location, urn, harnesses))

    return evaluate_constant_evidence(entries)


def test_no_live_smoke_harness_returns_constant_evidence() -> None:
    """No live_smoke harness returns fixed constant evidence that cannot fail."""
    assert_substrate_strict(
        _CONST_VALIDATOR_ID, collect_constant_evidence_violations()
    )


__all__ = [
    "detect_self_skip",
    "evaluate_live_smoke_execution",
    "collect_violations",
    "test_every_live_smoke_acceptance_executed",
    "detect_constant_evidence",
    "evaluate_constant_evidence",
    "collect_constant_evidence_violations",
    "test_no_live_smoke_harness_returns_constant_evidence",
]
