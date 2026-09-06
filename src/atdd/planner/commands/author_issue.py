# Component: component:author-atdd-substrate:author-issue-body:AuthorIssueBody:backend:application
"""`atdd author issue` — schema-driven issue-body authoring + validation (#1223).

The issue body is the last `atdd author` artifact without a schema. This module
gives it one: ``issue.schema.json`` (peer of convention-node/gate/relationship/
scope) is the single source of truth for which sections an issue body must
carry, and both the generator (:func:`create_issue_body`) and the schema-driven
gate (:func:`validate_issue_body`) project that schema rather than maintaining a
parallel ``REQUIRED_SUBSECTIONS`` / ``PLACEHOLDER_STRINGS`` list.

BOUNDARY: this lives planner-side (peer of ``create_convention_node``) and must
NOT ``import atdd.coach`` — ``author-atdd-substrate`` is a commons-themed wagon
(planner.theme.commons-coach-boundary, #970). The coach E019 gate may DELEGATE
to :func:`validate_issue_body`; the dependency points coach → planner, never the
reverse. The schema is read straight off disk from the planner schema home.

Status vocabulary is the single shared phase-machine vocabulary
(``phase_machine.convention.yaml``); the #1203 State-Store work-item record
reuses the same values (no fork) — see Decision #4 on #1223.
"""
from __future__ import annotations

import json
import re
from datetime import date
from functools import lru_cache
from pathlib import Path

# issue.schema.json sits beside the other authored-kind schemas.
SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schemas" / "author" / "issue.schema.json"


@lru_cache(maxsize=1)
def load_schema() -> dict:
    """Load and cache ``issue.schema.json`` (the single source of truth)."""
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def required_sections() -> list[str]:
    """The required section headings the schema declares (verbatim `##`/`###`)."""
    return list(load_schema().get("required", []))


def status_enum() -> list[str]:
    """The Metadata Status enum (the shared phase-machine vocabulary)."""
    return list(((load_schema().get("properties") or {}).get("status") or {}).get("enum") or [])


def issue_type_enum() -> list[str]:
    """The Metadata Type enum declared by ``issue.schema.json``."""
    return list(((load_schema().get("properties") or {}).get("type") or {}).get("enum") or [])


#: What an `## Artifacts` subsection carries when it has nothing to declare yet.
#:
#: Deliberately NOT a `- ` bullet: the parser reads bullets as claims, so any
#: bullet here would be a claim about a file. And deliberately not the
#: parenthesised `(none yet)` either — that string is a declared unfilled-template
#: placeholder (``issue_template.PLACEHOLDER_STRINGS``) which the E019 gate
#: rejects, so emitting it would trade one gate-invalid scaffold for another.
#:
#: An italic instruction is neither: it parses as zero artifacts, carries no
#: placeholder, and tells the worker exactly how to fill it (#1726).
EMPTY_DECLARATION = (
    "_Nothing declared yet — derive this section mechanically with "
    "`git diff --name-only origin/main..HEAD` before COMPLETE._"
)


@lru_cache(maxsize=1)
def _repo_relative_path_re():
    """The compiled `repoRelativePath` pattern the schema declares."""
    definitions = load_schema().get("definitions") or {}
    pattern = (definitions.get("repoRelativePath") or {}).get("pattern")
    if not pattern:  # pragma: no cover — the schema is shipped with the package
        raise ValueError(
            "issue.schema.json declares no definitions.repoRelativePath pattern; "
            "the authoring path cannot tell a repo-relative path from prose."
        )
    return re.compile(pattern)


def is_repo_relative_path(text: str) -> bool:
    """Whether *text* is a path the COMPLETE gate can resolve, per the schema.

    The one place that answers "is this bullet a claim or is it prose?". The
    `## Artifacts` section is resolved as real file paths by the COMPLETE gate
    while the schema typed it as a free-form string, so prose was as valid as a
    path until the gate rejected it (#1726). Both the generator and the coach
    checker read this, so neither can invent its own idea of a path.
    """
    return bool(_repo_relative_path_re().match((text or "").strip()))


# Matches a Metadata Status value in either the table form
# (``| Status | `INIT` |``) or a plain ``Status: INIT`` line. Only the first
# occurrence is read — the Metadata table is the first place Status appears.
_STATUS_RE = re.compile(r"(?im)^\s*\|?\s*Status\s*[:|]\s*`?\s*([A-Za-z][A-Za-z_-]*)")
_TYPE_RE = re.compile(r"(?im)^\s*\|?\s*Type\s*[:|]\s*`?\s*([A-Za-z][A-Za-z_-]*)")


def _extract_status(body: str) -> str | None:
    """Return the body's declared Status value, or ``None`` if it carries none."""
    m = _STATUS_RE.search(body)
    return m.group(1) if m else None


def extract_issue_type(body: str) -> str | None:
    """Return the body's declared Type value, or ``None`` if it carries none."""
    m = _TYPE_RE.search(body)
    return m.group(1) if m else None


def validate_issue_body(body: str) -> list[str]:
    """Validate an issue body against ``issue.schema.json``.

    Returns a list of human-readable violation strings; an empty list means the
    body is schema-valid. Supersedes/augments the E019 string-grep: the required
    sections and the Status enum are both read from the schema, not from a
    hard-coded list. A body that declares no Status is accepted (back-compat,
    K002) — only an out-of-enum Status is rejected (C010-UNIT-002). Type follows
    the same back-compat rule: legacy bodies without a Type row pass, but a body
    that declares Type must use the schema enum.
    """
    violations: list[str] = []

    for heading in required_sections():
        if heading not in body:
            violations.append(f"missing required section: {heading}")

    declared = _extract_status(body)
    if declared is not None:
        enum = status_enum()
        if declared not in enum:
            violations.append(
                f"invalid Status {declared!r}: not in the phase vocabulary "
                f"({', '.join(enum)})"
            )

    declared_type = extract_issue_type(body)
    if declared_type is not None:
        enum = issue_type_enum()
        if declared_type not in enum:
            violations.append(
                f"invalid Type {declared_type!r}: not in the issue type vocabulary "
                f"({', '.join(enum)})"
            )

    return violations


# ---------------------------------------------------------------------------
# Generator — emits a compliant-by-construction body (no placeholders).
# ---------------------------------------------------------------------------

def _bullets(items, fallback: str) -> str:
    items = [str(i).strip() for i in (items or []) if str(i).strip()]
    if not items:
        items = [fallback]
    return "\n".join(f"- {i}" for i in items)


def create_issue_body(spec: dict | None = None) -> str:
    """Render a schema-valid issue body from ``spec`` (compliant by construction).

    Emits every required section (all of :func:`required_sections`, including the
    mandatory ``### Graph Context`` / ``### Mirror Across Agents`` H3s), a
    Metadata table whose Status is drawn from the shared phase vocabulary, and
    zero template placeholders — so the output passes :func:`validate_issue_body`
    untouched. ``spec`` is the same minimal dict the other ``create_*`` authors
    accept; only ``title`` is really needed, the rest carry real defaults.
    """
    spec = dict(spec or {})
    title = str(spec.get("title") or "Untitled ATDD issue").strip()

    status = str(spec.get("status") or "INIT").strip()
    issue_type = str(spec.get("type") or "implementation").strip()
    branch = str(spec.get("branch") or "feat/unscoped").strip()
    archetypes = spec.get("archetypes") or ["planner"]
    archetypes_display = ", ".join(str(a) for a in archetypes)
    train = str(spec.get("train") or "0003-author-substrate").strip()
    feature = str(spec.get("feature") or "feature:author-atdd-substrate:author-issue-body").strip()

    scope = spec.get("scope") or {}
    in_scope = _bullets(scope.get("in_scope"), "The concrete deliverable this issue lands.")
    out_scope = _bullets(scope.get("out_of_scope"), "Work owned by sibling issues.")
    deps = _bullets(scope.get("dependencies"), "None.")
    done_when = _bullets(scope.get("done_when"), "The acceptances are green and the gate passes.")

    parts: list[str] = []

    parts.append(f"# {title}")

    parts.append(
        "## Issue Metadata\n\n"
        "| Field | Value |\n"
        "|-------|-------|\n"
        f"| Date | `{date.today().isoformat()}` |\n"
        f"| Status | `{status}` |\n"
        f"| Type | `{issue_type}` |\n"
        f"| Branch | `{branch}` |\n"
        f"| Archetypes | {archetypes_display} |\n"
        f"| Train | `{train}` |\n"
        f"| Feature | `{feature}` |"
    )

    parts.append(
        "## Scope\n\n"
        "### In Scope\n\n"
        f"{in_scope}\n\n"
        "### Out of Scope\n\n"
        f"{out_scope}\n\n"
        "### Dependencies\n\n"
        f"{deps}\n\n"
        "### Done-when\n\n"
        f"{done_when}"
    )

    parts.append(
        "## Context\n\n"
        "### Problem Statement\n\n"
        "| Aspect | Current | Target | Issue |\n"
        "|--------|---------|--------|-------|\n"
        f"| {title} | the gap exists today | the gap is closed | it blocks the substrate |\n\n"
        "### User Impact\n\n"
        "Authors and reviewers get a mechanically-checked artifact instead of a "
        "brittle manual one.\n\n"
        "### Root Cause\n\n"
        "The artifact predates the schema substrate and was governed by hand."
    )

    parts.append(
        "## Architecture\n\n"
        "### Graph Context\n\n"
        "This issue is authored from `issue.schema.json`; the schema owns the "
        "body shape and the generator/gate project it.\n\n"
        "### Mirror Across Agents\n\n"
        "| Agent | Current state | Target state | Action |\n"
        "|-------|---------------|--------------|--------|\n"
        "| planner | owns the schema + generator | unchanged | maintain |\n"
        "| tester | drift-guard pins the surfaces | unchanged | maintain |\n"
        "| coder | not involved in body shape | unchanged | none |\n"
        "| coach | gate delegates to the schema validator | unchanged | maintain |\n\n"
        "### Existing Patterns\n\n"
        "| Pattern | Example File | Convention |\n"
        "|---------|--------------|------------|\n"
        "| schema as source of truth | `convention-node.schema.json` | draft-07 |\n\n"
        "### Conceptual Model\n\n"
        "| Term | Definition | Example |\n"
        "|------|------------|---------|\n"
        "| schema-driven gate | the validator projects the schema | `validate_issue_body` |"
    )

    parts.append(
        "## Phases\n\n"
        "### Phase 1: Implement\n\n"
        "**Deliverables:**\n"
        "- The artifact this issue lands, authored from the schema.\n\n"
        "**Files:**\n\n"
        "| File | Change |\n"
        "|------|--------|\n"
        "| `issue.schema.json` | source of truth |"
    )

    parts.append(
        "## Validation\n\n"
        "### Gate Tests\n\n"
        "| ID | Phase | Command | Expected | ATDD Validator | Status |\n"
        "|----|-------|---------|----------|----------------|--------|\n"
        "| GT-001 | design | `atdd validate planner` | PASS | author tests | TODO |\n\n"
        "### Success Criteria\n\n"
        "- [ ] The body validates against `issue.schema.json`.\n"
        "- [ ] The schema-driven gate accepts it untouched."
    )

    parts.append(
        "## Decisions\n\n"
        "| # | Question | Decision | Rationale |\n"
        "|---|----------|----------|-----------|\n"
        "| 1 | Where does the body shape live? | planner `author` schema | parity with the other kinds |"
    )

    parts.append(
        "## Activity Log\n\n"
        f"### Entry 1 ({date.today().isoformat()})\n\n"
        "**Completed:**\n"
        "- Authored from `issue.schema.json` via `atdd author issue`.\n\n"
        "**Next:**\n"
        "- Fill in issue-specific detail and proceed through the phases."
    )

    parts.append(
        # The scaffold must be gate-valid on emission. It used to read
        # "- The artifact this issue lands." / "- None so far.", which parses as
        # THREE artifact claims and fails the COMPLETE gate — so the toolkit
        # shipped a body that was schema-valid and gate-invalid at the same
        # time, and the cheapest way to satisfy the gate was to delete the
        # section (#1726). The parenthesised form parses as zero claims: valid
        # at INIT, a completeness violation at COMPLETE, never a false claim.
        "## Artifacts\n\n"
        "### Created\n\n"
        f"{EMPTY_DECLARATION}\n\n"
        "### Modified\n\n"
        f"{EMPTY_DECLARATION}\n\n"
        "### Deleted\n\n"
        f"{EMPTY_DECLARATION}"
    )

    parts.append(
        "## Release Gate\n\n"
        "The release version lives in the State Store and is projected into the "
        "build automatically (#1172) — there is no version line to hand-edit.\n\n"
        "- [ ] Rebase on main.\n"
        "- [ ] `atdd state version bump --class PATCH|MINOR|MAJOR`\n"
        "- [ ] Merge the PR."
    )

    parts.append(
        "## Notes\n\n"
        "Authored compliant-by-construction from the canonical issue-body schema."
    )

    return "\n\n".join(parts) + "\n"
