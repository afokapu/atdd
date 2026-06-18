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

import os
import re
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Sequence, Tuple

import pytest

from atdd.coach.utils.repo import find_repo_root
from atdd.coach.utils.rule_binding import bind_rule
from atdd.coach.validators._violation import Violation
from atdd.tester.validators._acceptance_walker import (
    acceptance_urn,
    assert_substrate_strict,
    iter_repo_acceptances,
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

_ACCEPTANCE_HEADER_RE = re.compile(r"(?:#|//)\s*[Aa]cceptance:\s*(acc:[^\s]+)")
_TEST_FILENAME_RE = re.compile(
    r"^(?:test_.*\.py|.*_test\.py|.*\.test\.tsx?|.*\.spec\.ts|.*_test\.dart)$"
)
_TEST_EXTS = {".py", ".ts", ".tsx", ".dart"}
_PRUNE_DIRS = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    "dist",
    "build",
    ".tox",
    ".pytest_cache",
    ".mypy_cache",
    "site-packages",
}


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


def _walk_files(root: Path) -> Iterator[Path]:
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _PRUNE_DIRS]
        for fname in filenames:
            ext = "." + fname.rsplit(".", 1)[-1] if "." in fname else ""
            if ext.lower() not in _TEST_EXTS:
                continue
            yield Path(dirpath) / fname


def _scan_test_headers(repo_root: Path) -> Dict[str, List[Path]]:
    """Return ``{acceptance_urn: [test_file, ...]}`` for every anchored test."""
    index: Dict[str, List[Path]] = {}
    for test_file in _walk_files(repo_root):
        if not _TEST_FILENAME_RE.match(test_file.name):
            continue
        try:
            text = test_file.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        head = "\n".join(text.split("\n", 30)[:30])
        for match in _ACCEPTANCE_HEADER_RE.finditer(head):
            index.setdefault(match.group(1).strip(), []).append(test_file)
    return index


def collect_violations(repo_root: Optional[Path] = None) -> List[Violation]:
    """Walk plan/ for live_smoke acceptances and scan their anchored tests."""
    root = Path(repo_root).resolve() if repo_root is not None else find_repo_root()
    test_index = _scan_test_headers(root)

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


__all__ = [
    "detect_self_skip",
    "evaluate_live_smoke_execution",
    "collect_violations",
    "test_every_live_smoke_acceptance_executed",
]
