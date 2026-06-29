"""Shared helpers for the author-issue-body RED tests (#1223).

These tests anchor the four acceptances under
``plan/author_atdd_substrate/{E006,C010,C011,K002}.yaml``. They are written
at the RED phase: the schema (``issue.schema.json``), the generator
(``create_issue_body``), and the schema-driven validator
(``validate_issue_body``) do not exist yet, so every assertion below fails for
that reason and flips GREEN once those land. Nothing here is ``assert False``
theater — each test exercises the *eventual* capability against the real (future)
public surface.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from atdd.coach.utils.repo import find_repo_root

REPO_ROOT = find_repo_root()

# The canonical issue-body schema authored in Phase 1 (#1223). Peer of
# convention-node/gate/relationship/scope under planner/schemas/author/.
ISSUE_SCHEMA_PATH = (
    REPO_ROOT / "src" / "atdd" / "planner" / "schemas" / "author" / "issue.schema.json"
)

# The single shared vocabulary: the Metadata Status enum derives from
# phase_machine.convention.yaml (the same set the #1203 State-Store work-item
# record carries — do NOT fork). See C010-UNIT-002.
PHASE_ENUM = (
    "INIT",
    "PLANNED",
    "RED",
    "GREEN",
    "SMOKE",
    "REFACTOR",
    "COMPLETE",
    "BLOCKED",
    "OBSOLETE",
)


def load_issue_schema() -> dict:
    """Load issue.schema.json, asserting it exists (the RED tripwire)."""
    assert ISSUE_SCHEMA_PATH.exists(), (
        f"issue.schema.json not yet authored at "
        f"{ISSUE_SCHEMA_PATH.relative_to(REPO_ROOT)} — Phase 1 of #1223 (GREEN)"
    )
    return json.loads(ISSUE_SCHEMA_PATH.read_text(encoding="utf-8"))


def get_create_issue_body():
    """Return ``create_issue_body`` from the planner author command, or fail."""
    from atdd.planner.commands import author

    fn = getattr(author, "create_issue_body", None)
    assert fn is not None, (
        "atdd.planner.commands.author.create_issue_body not implemented yet "
        "— Phase 2 of #1223 (GREEN)"
    )
    return fn


def get_validate_issue_body():
    """Return the schema-driven ``validate_issue_body`` gate, or fail.

    The schema-driven validator supersedes the E019 string-grep
    (issue_template.check_body_sections / check_placeholders). It is expected to
    return a list of human-readable violation strings (empty list == valid).
    """
    from atdd.coach.commands import issue_template

    fn = getattr(issue_template, "validate_issue_body", None)
    assert fn is not None, (
        "atdd.coach.commands.issue_template.validate_issue_body not implemented "
        "yet — Phase 3 of #1223 (GREEN)"
    )
    return fn


def sample_spec() -> dict:
    """A minimal valid issue spec (Status drawn from the phase enum)."""
    return {
        "title": "Sample schema-driven issue",
        "status": "INIT",
        "type": "implementation",
        "branch": "feat/sample-schema-issue",
        "archetypes": ["planner"],
        "train": "0003-author-substrate",
        "feature": "feature:author-atdd-substrate:author-issue-body",
        "scope": {
            "in_scope": ["the issue body shape"],
            "out_of_scope": ["lifecycle/state (#1203)"],
            "dependencies": ["#1221"],
            "done_when": ["the body validates against issue.schema.json"],
        },
    }


def legacy_compliant_body() -> str:
    """Synthesize a body that passes *today's* E019 string-grep gate.

    Every required H2 section (from ``load_required_sections()``) plus the two
    required H3 subsections (``REQUIRED_SUBSECTIONS``), each filled with real
    prose, and zero ``PLACEHOLDER_STRINGS``. Derived from the live coach gate so
    the fixture cannot silently drift away from what E019 requires.
    """
    from atdd.coach.commands.issue_template import (
        REQUIRED_SUBSECTIONS,
        load_required_sections,
    )

    lines: list[str] = ["# Sample Compliant Issue", ""]
    for h2 in load_required_sections():
        lines += [h2, "", "Real, fully-authored content for this section.", ""]
        if h2 == "## Architecture":
            for h3 in REQUIRED_SUBSECTIONS:
                lines += [h3, "", "Real, fully-authored content.", ""]
    # Guarantee both required subsections are present even if the template's
    # H2 ordering ever drops `## Architecture`.
    for h3 in REQUIRED_SUBSECTIONS:
        if h3 not in "\n".join(lines):
            lines += [h3, "", "Real, fully-authored content.", ""]
    return "\n".join(lines)


def run_cli(*args: str) -> subprocess.CompletedProcess:
    """Run the repo CLI (``python -m atdd ...``) from a real checkout."""
    return subprocess.run(
        [sys.executable, "-m", "atdd", *args],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
