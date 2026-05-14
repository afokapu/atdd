"""
Template compliance helpers for GitHub issue bodies.

Parses `PARENT-ISSUE-TEMPLATE.md` at runtime so the template is the single
source of truth for required sections and placeholder patterns. Both
`atdd issue <N> --check` and the `--status` transition gate use this module.

SPEC IDs: SPEC-COACH-ORCH-0010, SPEC-COACH-ORCH-0011

NOTE: PR #271 (E010) is refactoring test_issue_validation.py to carry
`load_required_sections()` / `check_body_sections()`. This module is a
parallel implementation that avoids touching that file while PR #271 is
open; a follow-up refactor should consolidate the two after #271 merges.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

TEMPLATE_PATH = Path(__file__).parent.parent / "templates" / "PARENT-ISSUE-TEMPLATE.md"

# Literal placeholder strings that indicate an unfilled template region.
# Kept as a tuple so detection is conservative and auditable.
PLACEHOLDER_STRINGS: tuple[str, ...] = (
    "(define specific deliverables)",
    "(define explicit exclusions)",
    "(list session or external dependencies)",
    "(How does this problem affect users, developers, or the system?)",
    "(Why does this problem exist? What architectural or design decisions led to it?)",
    "(aspect)",
    "(current state)",
    "(target state)",
    "(why it's a problem)",
    "(pattern)",
    "(path)",
    "(convention file)",
    "(term)",
    "(definition)",
    "(example)",
    "(current architecture/structure)",
    "(target architecture/structure)",
    "(Name)",
    "(artifact)",
    "(description)",
    "(measurable outcome 1)",
    "(measurable outcome 2)",
    "(question)",
    "(decision)",
    "(rationale)",
    "(none yet)",
    "(Additional context, learnings, or decisions that don't fit elsewhere.)",
    "TBD",
    # New placeholders for Graph Context + Mirror Across Agents + Rule Wiring
    # (#682). The literal Graph Context placeholder also drives the planner
    # `planner.issue-body.graph-context-required` rule.
    "(graph context will be injected at creation by atdd issue <slug>)",
    "(current — observed/missing)",
    "(target — declared rule, validator, etc.)",
    "(action — add/update/none)",
    "(action)",
    "(rule_id)",
    "(1-5)",
    "(strict|suppress-and-clean|advisory|documentation-only)",
    "(validator module::function)",
    "(recipe or convention pointer)",
)

# Sections that are present in the template but NOT required for compliance.
# `## Rule Wiring` is OPTIONAL per #682 — it only applies to issues that
# introduce new convention rules; trivial issues may leave the section empty
# or omit it entirely.
OPTIONAL_SECTIONS: frozenset[str] = frozenset({"## Rule Wiring"})

# Subsections (H3) that ARE required to appear in every issue body. These are
# not surfaced by `load_required_sections()` (which only scans H2) but are
# enforced by `check_body_sections()`. Added in #682 to lift the
# Architecture > Graph Context and Architecture > Mirror Across Agents
# subsections from advisory to mandatory.
REQUIRED_SUBSECTIONS: tuple[str, ...] = (
    "### Graph Context",
    "### Mirror Across Agents",
)


@dataclass
class ComplianceReport:
    """Structured result of a template compliance check."""
    issue_number: int
    missing_sections: list[str] = field(default_factory=list)
    placeholder_hits: list[tuple[str, str]] = field(default_factory=list)

    @property
    def compliant(self) -> bool:
        return not self.missing_sections and not self.placeholder_hits

    def format(self) -> str:
        if self.compliant:
            return f"✓ #{self.issue_number}: template compliant"
        lines = [f"❌ #{self.issue_number}: template non-compliant"]
        if self.missing_sections:
            lines.append(f"  Missing sections ({len(self.missing_sections)}):")
            for s in self.missing_sections:
                lines.append(f"    - {s}")
        if self.placeholder_hits:
            lines.append(f"  Unfilled placeholders ({len(self.placeholder_hits)}):")
            for section, placeholder in self.placeholder_hits:
                lines.append(f"    - {section}: {placeholder}")
        lines.append("")
        lines.append("Fix: edit the issue body on GitHub and replace placeholders with real content.")
        lines.append("     `gh issue edit <N>` or the GitHub web UI.")
        return "\n".join(lines)


def load_required_sections(template_path: Path = TEMPLATE_PATH) -> list[str]:
    """Extract all `## ` H2 headings from the parent issue template.

    Returns them in the order they appear in the template. This is the
    single source of truth for which sections an issue body must contain.
    """
    if not template_path.exists():
        return []
    sections: list[str] = []
    for line in template_path.read_text().splitlines():
        stripped = line.rstrip()
        if stripped.startswith("## ") and not stripped.startswith("### "):
            sections.append(stripped)
    return sections


def check_body_sections(
    body: str,
    required: list[str] | None = None,
) -> list[str]:
    """Return the list of required sections missing from `body`.

    Filters out `OPTIONAL_SECTIONS` (e.g. `## Rule Wiring`) and also
    enforces presence of every entry in `REQUIRED_SUBSECTIONS` (H3 sections
    under `## Architecture` that #682 lifted from advisory to mandatory).
    """
    required = required or load_required_sections()
    missing = [s for s in required if s not in body and s not in OPTIONAL_SECTIONS]
    missing.extend(s for s in REQUIRED_SUBSECTIONS if s not in body)
    return missing


def _iter_section_slices(body: str) -> list[tuple[str, str]]:
    """Split a body into (section_heading, section_text) pairs.

    Anything before the first `## ` heading is returned under a synthetic
    "(preamble)" key.
    """
    slices: list[tuple[str, str]] = []
    current_name = "(preamble)"
    current_lines: list[str] = []
    for line in body.splitlines():
        if line.startswith("## ") and not line.startswith("### "):
            slices.append((current_name, "\n".join(current_lines)))
            current_name = line.rstrip()
            current_lines = []
        else:
            current_lines.append(line)
    slices.append((current_name, "\n".join(current_lines)))
    return slices


def check_placeholders(
    body: str,
    placeholders: tuple[str, ...] = PLACEHOLDER_STRINGS,
) -> list[tuple[str, str]]:
    """Return (section_heading, placeholder_string) for every unfilled placeholder.

    Only placeholder strings that *literally* appear in the body are flagged.
    This avoids regex false positives on user content.

    Skips OPTIONAL sections (`## Rule Wiring`) — authors who don't introduce
    new rules may leave that scaffold's placeholder text intact.
    """
    hits: list[tuple[str, str]] = []
    for heading, text in _iter_section_slices(body):
        if heading == "(preamble)":
            continue
        if heading in OPTIONAL_SECTIONS:
            continue
        for placeholder in placeholders:
            if placeholder in text:
                hits.append((heading, placeholder))
    return hits


def check_issue_compliance(
    issue_number: int,
    body: str,
) -> ComplianceReport:
    """Run the full section + placeholder check on an issue body."""
    return ComplianceReport(
        issue_number=issue_number,
        missing_sections=check_body_sections(body),
        placeholder_hits=check_placeholders(body),
    )
