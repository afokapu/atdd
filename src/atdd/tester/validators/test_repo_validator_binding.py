# URN: component:govern-lifecycle:enforcement-substrate:test_repo_validator_binding:backend:tests
# Runtime: python
# Purpose: Substrate enforcement (#410) — when harness.type is declared, an anchored test must exist with matching headers.

"""Substrate Class 1 conformance: bidirectional repo binding (spec v12 §7.3).

Distinct from the toolkit-side
``src/atdd/coach/validators/test_rule_validator_binding.py`` (which
validates toolkit rule → validator binding via convention metadata).
This validator validates the *repo* side: every acceptance with
``harness.type`` set must have at least one anchored test file whose
``# Acceptance: <urn>`` header points back at it.

The substrate doesn't duplicate header-presence enforcement (already
done by ``atdd repo validate`` via TestResolver — spec §7.3 line 551).
This validator catches the orthogonal failure: header is *present* but
the bidirectional pair is broken — acceptance has no test, or the
acceptance URN named in a header doesn't resolve to a real acceptance.

Failures route through ``assert_disposition_satisfied`` under
``tester.acceptance-violation.validator-binding-must-be-bidirectional``
(strict).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Set

import pytest

from atdd.coach.utils.disposition_gate import assert_disposition_satisfied
from atdd.coach.utils.repo import find_repo_root
from atdd.coach.utils.rule_binding import bind_rule
from atdd.coach.validators._violation import Violation
from atdd.tester.validators._acceptance_walker import (
    acceptance_urn,
    has_harness_type,
    iter_repo_acceptances,
)


pytestmark = [pytest.mark.platform]


_RULE = bind_rule(
    "tester.acceptance-violation.validator-binding-must-be-bidirectional"
)
_VALIDATOR_ID = (
    "test_repo_validator_binding::test_validator_binding_is_bidirectional"
)

_ACCEPTANCE_HEADER_RE = re.compile(
    r"(?:#|//)\s*[Aa]cceptance:\s*(acc:[^\s]+)"
)
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


def _iter_test_files(repo_root: Path) -> Iterator[Path]:
    """Walk the repo for files whose names match the test pattern."""
    for path in _walk_files(repo_root):
        if _TEST_FILENAME_RE.match(path.name):
            yield path


def _walk_files(root: Path) -> Iterator[Path]:
    """Walk *root* yielding files, pruning vendored/build dirs."""
    import os

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
    for test_file in _iter_test_files(repo_root):
        try:
            text = test_file.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        # Only inspect the leading comment block (first ~30 lines is enough
        # for any well-formed header). Avoids false positives from prose
        # mentioning "# Acceptance: acc:..." inside the test body.
        head = "\n".join(text.split("\n", 30)[:30])
        for match in _ACCEPTANCE_HEADER_RE.finditer(head):
            urn = match.group(1).strip()
            index.setdefault(urn, []).append(test_file)
    return index


def collect_violations(repo_root: Optional[Path] = None) -> List[Violation]:
    """Walk plan/ + tests and return bidirectional-binding violations."""
    root = Path(repo_root).resolve() if repo_root is not None else find_repo_root()
    violations: List[Violation] = []

    test_index: Dict[str, List[Path]] = _scan_test_headers(root)
    declared_acc_urns: Set[str] = set()

    # Forward pass: every acceptance with harness.type must have a test.
    for raw in iter_repo_acceptances(root):
        urn = acceptance_urn(raw.body)
        if not urn:
            # Missing URN is policed by URN-graph validators; skip here so we
            # don't double-emit on the same site.
            continue
        declared_acc_urns.add(urn)

        if not has_harness_type(raw.body):
            continue

        if urn not in test_index:
            violations.append(
                Violation(
                    rule_id=_RULE.rule_id,
                    severity=_RULE.severity,
                    location=raw.location,
                    detail=(
                        f"acceptance {urn!r} declares harness.type but no test "
                        f"file carries '# Acceptance: {urn}' in its header — "
                        f"binding is one-way"
                    ),
                    fix_hint_ref=_RULE.fix_hint_ref,
                )
            )

    # Reverse pass: every test header that names an acc:* URN must resolve
    # to a real acceptance. Anchored-but-orphaned tests fail this rule too.
    for urn, files in test_index.items():
        if urn in declared_acc_urns:
            continue
        for test_file in files:
            try:
                rel = str(test_file.resolve().relative_to(root.resolve()))
            except ValueError:
                rel = str(test_file)
            violations.append(
                Violation(
                    rule_id=_RULE.rule_id,
                    severity=_RULE.severity,
                    location=rel,
                    detail=(
                        f"test {rel!r} anchors to {urn!r} but no acceptance "
                        f"with that URN exists in plan/ — binding is one-way"
                    ),
                    fix_hint_ref=_RULE.fix_hint_ref,
                )
            )

    return violations


def test_validator_binding_is_bidirectional() -> None:
    """Every acceptance ↔ anchored test pair must resolve in BOTH directions (§7.3)."""
    violations = collect_violations()
    assert_disposition_satisfied(_VALIDATOR_ID, violations)


__all__ = ["collect_violations", "test_validator_binding_is_bidirectional"]
