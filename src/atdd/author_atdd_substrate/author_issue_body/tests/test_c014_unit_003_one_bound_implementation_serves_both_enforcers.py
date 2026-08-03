# URN: test:author-atdd-substrate:author-issue-body:C014-UNIT-003-one-bound-implementation-serves-both-enforcers
# Acceptance: acc:author-atdd-substrate:C014-UNIT-003-one-bound-implementation-serves-both-enforcers
# WMBT: wmbt:author-atdd-substrate:C014
# Phase: RED
# Layer: application
"""C014-UNIT-003 — exactly one bound implementation of the artifact policy.

There is no convention rule, so there is nothing for either enforcer to bind
to, and each invented its own policy — including the same escape. Fixing the
two implementations alone leaves them free to drift apart again; the rule is
what makes them bindable.

This is the acceptance that fails if a second copy of the ``total == 0`` escape
ever reappears in either enforcer, or if the shared checker stops binding its
rules at module-import time.
"""
from __future__ import annotations

import re
from pathlib import Path

import atdd

_PKG = Path(atdd.__file__).resolve().parent

_SHARED_CHECKER = _PKG / "coach" / "utils" / "artifact_claims.py"
_RUNTIME_GATE = _PKG / "coach" / "commands" / "issue.py"
_VALIDATOR = _PKG / "coach" / "validators" / "test_issue_gate_completion.py"

# The escape, in the shape both enforcers wrote it: a total over the parsed
# claim groups, tested against zero.
_ESCAPE = re.compile(
    r"sum\(\s*len\(v\)\s*for\s*v\s*in\s*artifacts\.values\(\)\s*\)"
    r"|total\s*==\s*0"
)

# ``_RULE = bind_rule("...")`` at column 0 — module-import time, not inside a
# function where it would only fire when the code path runs.
_MODULE_LEVEL_BIND = re.compile(r"^[A-Z_][A-Z_0-9]*\s*=\s*bind_rule\(", re.MULTILINE)


def test_c014_unit_003_the_shared_checker_binds_its_rules_at_import_time():
    from atdd.coach.utils.artifact_claims import (
        BOUND_RULES,
        RULE_CLAIMS_RESOLVE,
        RULE_MUST_BE_DECLARED,
    )

    assert set(BOUND_RULES) == {RULE_CLAIMS_RESOLVE, RULE_MUST_BE_DECLARED}, (
        "the shared checker must resolve every rule it emits through bind_rule "
        "at module-import time (SPEC-COACH-RULEID-0007)"
    )
    for rule_id, meta in BOUND_RULES.items():
        assert meta.rule_id == rule_id


def test_c014_unit_003_the_validator_binds_and_delegates():
    """The COMPLETE-gate validator calls ``bind_rule`` and owns no policy of its own."""
    source = _VALIDATOR.read_text(encoding="utf-8")

    assert _MODULE_LEVEL_BIND.search(source), (
        "test_issue_gate_completion.py calls bind_rule zero times while guarding "
        "the COMPLETE gate — CLAUDE.md requires the module-import-time binding"
    )
    assert "artifact_claims" in source, (
        "the validator must delegate to the shared checker, not carry its own copy"
    )


def test_c014_unit_003_neither_enforcer_carries_its_own_escape():
    """The ``total == 0`` free pass exists in the shared checker's policy or nowhere."""
    offenders = []
    for path in (_RUNTIME_GATE, _VALIDATOR):
        source = path.read_text(encoding="utf-8")
        for lineno, line in enumerate(source.splitlines(), start=1):
            if line.lstrip().startswith("#"):
                continue  # a comment about the escape is history, not policy
            if _ESCAPE.search(line):
                offenders.append(f"{path.name}:{lineno}: {line.strip()}")

    assert not offenders, (
        "a second copy of the artifact-count escape reappeared — the policy must "
        "live in atdd/coach/utils/artifact_claims.py and nowhere else:\n  "
        + "\n  ".join(offenders)
    )


def test_c014_unit_003_the_runtime_gate_delegates_to_the_shared_checker():
    source = _RUNTIME_GATE.read_text(encoding="utf-8")
    assert "artifact_claims" in source, (
        "IssueManager must answer the artifacts question from the shared checker"
    )


def test_c014_unit_003_the_shared_checker_exists_exactly_once():
    """No sibling module re-implements the policy the checker owns."""
    assert _SHARED_CHECKER.is_file(), f"{_SHARED_CHECKER} does not exist"

    duplicates = []
    for path in sorted(_PKG.rglob("*.py")):
        if path == _SHARED_CHECKER or "tests" in path.parts:
            continue
        source = path.read_text(encoding="utf-8", errors="replace")
        if "def check_artifact_claims" in source:
            duplicates.append(str(path.relative_to(_PKG)))

    assert not duplicates, f"the policy is implemented more than once: {duplicates}"
