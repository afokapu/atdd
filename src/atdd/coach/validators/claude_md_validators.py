# URN: component:spawn-agents:claude-md-slim-and-debanner:claude_md_validators:backend:domain
# Runtime: python
# Purpose: Validators for CLAUDE.md content quality (R002/R003).
"""
Validators for CLAUDE.md content quality.

Two rules:
  coach.claude_md.size_budget
      CLAUDE.md must be ≤ 250 lines (worker context budget).
      Registered by R002.

  coach.claude_md.no_bypass_advertising
      CLAUDE.md must not contain ATDD_SKIP_* env-var tokens.
      Registered by R003.

Usage (from validate coach suite or directly):
    from atdd.coach.validators.claude_md_validators import (
        validate_claude_md_size_budget,
        validate_claude_md_no_bypass_advertising,
    )
    violations = validate_claude_md_size_budget(Path("CLAUDE.md"))
    violations = validate_claude_md_no_bypass_advertising(Path("CLAUDE.md"))

Both functions return 0 (int) when there are no violations.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Union

_LINE_BUDGET = 250
_BYPASS_PATTERN = re.compile(r"ATDD_SKIP_[A-Z_]+")

# Rule IDs emitted in validate coach output so smoke tests can grep for them.
RULE_ID_SIZE_BUDGET = "coach.claude_md.size_budget"
RULE_ID_NO_BYPASS_ADVERTISING = "coach.claude_md.no_bypass_advertising"


def validate_claude_md_size_budget(path: Union[str, Path]) -> int:
    """Validate that CLAUDE.md has ≤ 250 lines (worker context budget).

    Rule: coach.claude_md.size_budget (sev 3, strict)

    Emits the rule ID on every run so that `atdd validate coach` output always
    contains the rule ID (R002-SMOKE-001 greps for it regardless of outcome).

    Args:
        path: Path to the CLAUDE.md file to validate.

    Returns:
        0 if the file is within the line budget.
        A positive integer (violation count) if the budget is exceeded.
    """
    p = Path(path)
    lines = p.read_text(encoding="utf-8").splitlines()
    line_count = len(lines)

    if line_count <= _LINE_BUDGET:
        print(
            f"[{RULE_ID_SIZE_BUDGET}] PASS: {p.name} has {line_count} lines "
            f"(budget: {_LINE_BUDGET})"
        )
        return 0

    # Return a non-zero violation count; the excess lines are the primary metric.
    excess = line_count - _LINE_BUDGET
    print(
        f"[{RULE_ID_SIZE_BUDGET} sev=3] {p.name}:1: "
        f"{line_count} lines exceeds the {_LINE_BUDGET}-line budget by {excess} lines. "
        "Trim CLAUDE.md — move detailed notes to src/atdd/ conventions."
    )
    return excess


def validate_claude_md_no_bypass_advertising(path: Union[str, Path]) -> int:
    """Validate that CLAUDE.md contains no ATDD_SKIP_* env-var tokens.

    Rule: coach.claude_md.no_bypass_advertising (sev 3, strict)

    Emits the rule ID on every run so that `atdd validate coach` output always
    contains the rule ID (R003-SMOKE-001 greps for it regardless of outcome).

    Agents reading CLAUDE.md must not discover inline bypass env-vars they
    could copy-paste. The correct operator override path is:
        atdd emergency --reason '<reason>'
    documented in docs/operator-emergency-bypass.md.

    Args:
        path: Path to the CLAUDE.md file to validate.

    Returns:
        0 if no bypass tokens are found.
        A positive integer (violation count) equal to the number of matched lines.
    """
    p = Path(path)
    lines = p.read_text(encoding="utf-8").splitlines()

    offending = [
        (i + 1, line)
        for i, line in enumerate(lines)
        if _BYPASS_PATTERN.search(line)
    ]

    if not offending:
        print(
            f"[{RULE_ID_NO_BYPASS_ADVERTISING}] PASS: {p.name} contains no ATDD_SKIP_* tokens"
        )
        return 0

    for lineno, line in offending:
        print(
            f"[{RULE_ID_NO_BYPASS_ADVERTISING} sev=3] {p.name}:{lineno}: "
            f"bypass token found: '{_BYPASS_PATTERN.search(line).group()}'. "
            "Remove ATDD_SKIP_* tokens; use 'atdd emergency --reason' instead."
        )
    return len(offending)


__all__ = [
    "validate_claude_md_size_budget",
    "validate_claude_md_no_bypass_advertising",
    "RULE_ID_SIZE_BUDGET",
    "RULE_ID_NO_BYPASS_ADVERTISING",
]
