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
from functools import lru_cache
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

# --- The contract has ONE source: issue.schema.json (#1901) ----------------
#
# It had two. The author rendered from `issue.schema.json` (13 required
# sections); the coach validated from `PARENT-ISSUE-TEMPLATE.md` (12). The two
# constants below were the difference between them, maintained BY HAND:
#
#     OPTIONAL_SECTIONS     template-only  ->  ## Rule Wiring
#     REQUIRED_SUBSECTIONS  schema-only    ->  ### Graph Context, ### Mirror Across Agents
#
# So they were not policy. They were the drift, written down — and when #682
# moved the schema, one reader followed and another did not. Measured over 40
# open issues before this change: 38 were rejected by the template-only reader
# ALONE, and not one issue in the repository satisfied both.
#
# Both names survive with the SAME values, because a dozen call sites use them —
# but they are now DERIVED from the two artifacts rather than typed out, so the
# next time schema and template move apart the difference follows automatically
# instead of being discovered by a broken CI run.

SCHEMA_PATH = (
    Path(__file__).resolve().parents[2]
    / "planner" / "schemas" / "author" / "issue.schema.json"
)


@lru_cache(maxsize=1)
def _schema_required() -> tuple[str, ...]:
    """The section headings `issue.schema.json` declares required.

    Empty when the schema is absent — the callers below then fall back to the
    template, which is the pre-#1901 behaviour and keeps a checkout without the
    planner package working rather than silently requiring nothing.
    """
    if not SCHEMA_PATH.exists():
        return ()
    import json

    return tuple(json.loads(SCHEMA_PATH.read_text(encoding="utf-8")).get("required", []))


def _template_h2() -> tuple[str, ...]:
    """Every `## ` heading in the human template, in order."""
    if not TEMPLATE_PATH.exists():
        return ()
    return tuple(
        line.rstrip()
        for line in TEMPLATE_PATH.read_text().splitlines()
        if line.startswith("## ") and not line.startswith("### ")
    )


def _optional_sections() -> frozenset[str]:
    """Template headings the schema does not require.

    `## Rule Wiring` is the current member: it applies only to issues that
    introduce convention rules (#682), so the template offers it and the
    contract does not demand it.
    """
    required = set(_schema_required())
    if not required:
        return frozenset({"## Rule Wiring"})
    return frozenset(h for h in _template_h2() if h not in required)


OPTIONAL_SECTIONS: frozenset[str] = _optional_sections()

# Subsections (H3) that ARE required to appear in every issue body. These are
# not surfaced by `load_required_sections()` (which only scans H2) but are
# enforced by `check_body_sections()`. Added in #682 to lift the
# Architecture > Graph Context and Architecture > Mirror Across Agents
# subsections from advisory to mandatory.
def _required_subsections() -> tuple[str, ...]:
    """Schema-required headings the H2 template scan cannot surface.

    `load_required_sections()` returns H2 headings only, so the H3 sections #682
    lifted from advisory to mandatory have to be carried separately. Derived from
    the schema rather than typed out, so "mandatory" means one thing.
    """
    required = _schema_required()
    if not required:
        return ("### Graph Context", "### Mirror Across Agents")
    return tuple(h for h in required if h.startswith("### "))


REQUIRED_SUBSECTIONS: tuple[str, ...] = _required_subsections()


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


def _is_unfilled(line: str, placeholder: str) -> bool:
    """Is *line* the placeholder itself, rather than a mention of it?

    Strips list bullets, markdown emphasis, backticks and enclosing brackets, so
    `- _(example)_` still counts as unfilled while a sentence that happens to
    contain the word does not.
    """
    stripped = line.strip().lstrip("-*+ \t").strip()
    for ch in ("_", "*", "`"):
        stripped = stripped.strip(ch)
    stripped = stripped.strip()
    return stripped == placeholder or stripped == placeholder.strip("()")


def check_placeholders(
    body: str,
    placeholders: tuple[str, ...] = PLACEHOLDER_STRINGS,
) -> list[tuple[str, str]]:
    """Return (section_heading, placeholder_string) for every unfilled placeholder.

    A placeholder is UNFILLED when it is the whole content of a line — that is
    what "the author did not replace the scaffold" looks like. It is not a
    substring anywhere in the section (#1904).

    The substring form flagged, among 120 open issues, four hits and zero real
    ones. All four were prose:

        DEFINE = "define"      # find the JTBD main job        <- 'JTBD'
        | 9 | Which predecessor is the pilot? | TBD — chosen before RED
        honestly-broken values (`TBD` 34, `none` 14, `N/A` 7)
        34  TBD                                                <- a count OF TBDs

    The first is decisive: "JTBD" contains "TBD". A Jobs-To-Be-Done comment read
    as an unfilled section. The second is worse than harmless — a Decisions table
    recording a pending decision is that table doing its job, and the check
    punished it.

    Markdown emphasis, backticks and surrounding parens are stripped before the
    comparison, because the template ships several placeholders already wrapped
    that way and an author who leaves `_TBD_` has still left it.

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
            if any(_is_unfilled(line, placeholder) for line in text.splitlines()):
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
