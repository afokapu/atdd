# URN: component:govern-lifecycle:enforcement-substrate:test_conductor_md_no_duplicated_convention:backend:domain
# Runtime: python
# Purpose: Enforces coach.template.no-duplicated-convention — forbids re-introduction
#          of convention content into the agent-facing CONDUCTOR.md template (#919).
"""
Validator for ``coach.template.no-duplicated-convention``.

CONDUCTOR.md (``src/atdd/coach/templates/CONDUCTOR.md``) is the
agent-facing instruction file that ships into every consumer repo via
``atdd sync``. Its job is to bootstrap the agent and point at canonical
sources — NOT to be a second copy of those sources.

The Coach Decomposition (#887) has been actively removing duplicated
convention content from the template (state_machine in #888;
``atdd_cycle.phases``, ``audits.*``, ``infrastructure.*``,
``architecture.*``, ``testing.*``, ``agents.*``, ``conventions:``,
``manifest:``, and ``tests:`` in #919). Without a substrate rule,
future PRs can quietly re-introduce the bloat.

Convention: ``src/atdd/coach/conventions/template.convention.yaml``
            (rule ``coach.template.no-duplicated-convention``)

Emits structured ``Violation`` records the disposition gate fails
on under ``strict`` disposition.
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Tuple

import pytest

import atdd
from atdd.coach.utils.disposition_gate import assert_disposition_satisfied
from atdd.coach.utils.rule_binding import bind_rule
from atdd.coach.validators._violation import Violation


pytestmark = [pytest.mark.coach]


_RULE = bind_rule("coach.template.no-duplicated-convention")
_VALIDATOR_ID = "test_conductor_md_no_duplicated_convention"

_CONDUCTOR_MD = (
    Path(atdd.__file__).resolve().parent
    / "coach"
    / "templates"
    / "CONDUCTOR.md"
)

# Each entry: (forbidden_top_level_header, canonical_source_pointer).
# Order is the order they are emitted — keep stable for deterministic test output.
_FORBIDDEN_SECTIONS: Tuple[Tuple[str, str], ...] = (
    ("manifest:", "derivable from the filesystem / `atdd gate`"),
    ("tests:", "pytest collection (filesystem discovery)"),
    ("audits:", "`atdd validate --help` and `atdd repo --help`"),
    (
        "atdd_cycle:",
        "src/atdd/coach/conventions/phase_machine.convention.yaml "
        "(§4.5; already excised in #888 — keep it gone)",
    ),
    (
        "infrastructure:",
        "src/atdd/tester/conventions/contract.convention.yaml and "
        "src/atdd/coder/conventions/technology.convention.yaml",
    ),
    (
        "architecture:",
        "src/atdd/coder/conventions/backend.convention.yaml and "
        "src/atdd/coder/conventions/boundaries.convention.yaml",
    ),
    ("testing:", "src/atdd/tester/conventions/"),
    ("agents:", "src/atdd/{planner,tester,coder}/conventions/"),
    ("conventions:", "the filesystem (`ls src/atdd/*/conventions/`)"),
)


def _scan_conductor_md_for_forbidden_sections() -> List[Violation]:
    """Walk CONDUCTOR.md and emit one Violation per forbidden top-level header.

    A "top-level" header is matched at column 0 (no leading whitespace) so
    that nested keys whose names happen to collide do not false-positive.
    """
    if not _CONDUCTOR_MD.exists():
        # Treat missing template as a substrate fault, not a violation of
        # this rule — let other tests catch it.
        return []

    violations: List[Violation] = []
    text = _CONDUCTOR_MD.read_text()
    lines = text.splitlines()

    # Build a quick header -> canonical mapping for O(N) scan.
    forbidden_map = dict(_FORBIDDEN_SECTIONS)

    for line_number, line in enumerate(lines, start=1):
        if line.startswith(" ") or line.startswith("\t"):
            continue
        # Match a YAML top-level mapping key: "<header>" optionally followed
        # by trailing whitespace and an inline comment.
        stripped = line.rstrip()
        for header, canonical in forbidden_map.items():
            if stripped == header or stripped.startswith(header):
                # Confirm the header is THE top-level key, not e.g.
                # "manifest_legacy:" — the next char after the colon must be
                # end-of-line or whitespace.
                tail = stripped[len(header):]
                if tail and not tail[0].isspace():
                    continue
                violations.append(
                    Violation(
                        rule_id=_RULE.rule_id,
                        severity=_RULE.severity,
                        location=f"src/atdd/coach/templates/CONDUCTOR.md:{line_number}",
                        detail=(
                            f"CONDUCTOR.md re-introduces forbidden top-level "
                            f"section {header!r} (line {line_number}). Canonical "
                            f"home: {canonical}. Delete the section and leave a "
                            f"single-line pointer comment if agents need a "
                            f"breadcrumb."
                        ),
                        fix_hint_ref=getattr(_RULE, "fix_hint_ref", None),
                    )
                )
                break  # one violation per line is enough
    return violations


def test_conductor_md_does_not_duplicate_convention_content() -> None:
    """CONDUCTOR.md must not carry top-level sections that duplicate convention YAMLs."""
    violations = _scan_conductor_md_for_forbidden_sections()
    assert_disposition_satisfied(
        validator_id=_VALIDATOR_ID,
        violations=violations,
    )
