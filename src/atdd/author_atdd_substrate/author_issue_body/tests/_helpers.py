"""Shared helpers for the author-issue-body RED tests (#1223).

These tests anchor the four acceptances under
``plan/author_atdd_substrate/{E006,C010,C011,K002}.yaml``. They are written at
the RED phase: the schema (``issue.schema.json``), the generator
(``create_issue_body``), and the schema-driven validator (``validate_issue_body``)
do not exist yet, so every assertion below fails for that reason and flips GREEN
once those land. Nothing here is ``assert False`` theater — each test exercises the
*eventual* capability against the real (future) public surface.

BOUNDARY: ``author-atdd-substrate`` is a ``commons``-themed wagon, so nothing in
this tree may ``import atdd.coach`` (planner.theme.commons-coach-boundary, #970).
The legacy E019 gate's required-section set is therefore reconstructed by reading
``PARENT-ISSUE-TEMPLATE.md`` directly — the very file ``load_required_sections()``
parses — rather than importing ``atdd.coach.commands.issue_template``. Reading the
gate's own source-of-truth keeps the drift-guard faithful without crossing the
boundary.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def _find_repo_root() -> Path:
    """Walk up from this file until a repo marker (pyproject.toml) is found."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").exists():
            return parent
    raise RuntimeError("could not locate repo root from " + str(here))


REPO_ROOT = _find_repo_root()

# The canonical issue-body schema authored in Phase 1 (#1223). Peer of
# convention-node/gate/relationship/scope under planner/schemas/author/.
ISSUE_SCHEMA_PATH = (
    REPO_ROOT / "src" / "atdd" / "planner" / "schemas" / "author" / "issue.schema.json"
)

# The legacy gate's source of truth (parsed by load_required_sections()).
TEMPLATE_PATH = (
    REPO_ROOT / "src" / "atdd" / "coach" / "templates" / "PARENT-ISSUE-TEMPLATE.md"
)

# Mirrors atdd.coach.commands.issue_template.REQUIRED_SUBSECTIONS (#682): the two
# H3 subsections lifted from advisory to mandatory.
REQUIRED_SUBSECTIONS: tuple[str, ...] = (
    "### Graph Context",
    "### Mirror Across Agents",
)

# Mirrors atdd.coach.commands.issue_template.OPTIONAL_SECTIONS (#682): present in
# the template but NOT required for compliance.
OPTIONAL_SECTIONS: frozenset[str] = frozenset({"## Rule Wiring"})

# A representative subset of issue_template.PLACEHOLDER_STRINGS — enough to prove a
# generated/fixture body carries no unfilled-template traps. (Local copy; the
# canonical list lives coach-side and the schema-driven gate is the real check.)
PLACEHOLDER_PROBES: tuple[str, ...] = (
    "TBD",
    "(define specific deliverables)",
    "(graph context will be injected at creation by atdd issue <slug>)",
    "(measurable outcome 1)",
    "(none yet)",
    "(rule_id)",
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


def load_required_sections() -> list[str]:
    """Reconstruct the gate's required H2 sections from the template file.

    Mirrors atdd.coach.commands.issue_template.load_required_sections() by
    reading PARENT-ISSUE-TEMPLATE.md (its source of truth) without importing the
    coach package.
    """
    if not TEMPLATE_PATH.exists():
        return []
    sections: list[str] = []
    for line in TEMPLATE_PATH.read_text(encoding="utf-8").splitlines():
        stripped = line.rstrip()
        if stripped.startswith("## ") and not stripped.startswith("### "):
            sections.append(stripped)
    return sections


def required_section_set() -> set[str]:
    """The gate's effective must-be-present set (H2 minus optional, plus H3s)."""
    return (set(load_required_sections()) - set(OPTIONAL_SECTIONS)) | set(
        REQUIRED_SUBSECTIONS
    )


def legacy_missing_sections(body: str) -> list[str]:
    """Mirror of issue_template.check_body_sections()."""
    missing = [
        s
        for s in load_required_sections()
        if s not in body and s not in OPTIONAL_SECTIONS
    ]
    missing.extend(s for s in REQUIRED_SUBSECTIONS if s not in body)
    return missing


def legacy_placeholder_hits(body: str) -> list[str]:
    """Mirror of issue_template.check_placeholders() over the probe subset."""
    return [p for p in PLACEHOLDER_PROBES if p in body]


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

    The schema-driven validator supersedes the E019 string-grep and is expected
    to return a list of human-readable violation strings (empty list == valid).
    It is co-located with ``create_issue_body`` in the planner author module
    (schema-driven validation beside schema-driven generation, both off the
    planner-owned ``issue.schema.json``); the coach E019 gate delegates to it.
    Resolving it planner-side keeps this commons-themed tree off ``atdd.coach``
    (planner.theme.commons-coach-boundary, #970).
    """
    from atdd.planner.commands import author

    fn = getattr(author, "validate_issue_body", None)
    assert fn is not None, (
        "atdd.planner.commands.author.validate_issue_body not implemented yet "
        "— Phase 3 of #1223 (GREEN)"
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

    Every required H2 section (from the template) plus the two required H3
    subsections, each filled with real prose, and zero placeholder probes.
    """
    lines: list[str] = ["# Sample Compliant Issue", ""]
    for h2 in load_required_sections():
        lines += [h2, "", "Real, fully-authored content for this section.", ""]
        if h2 == "## Architecture":
            for h3 in REQUIRED_SUBSECTIONS:
                lines += [h3, "", "Real, fully-authored content.", ""]
    rendered = "\n".join(lines)
    for h3 in REQUIRED_SUBSECTIONS:
        if h3 not in rendered:
            lines += [h3, "", "Real, fully-authored content.", ""]
    return "\n".join(lines)


def run_cli(*args: str, env: dict | None = None) -> subprocess.CompletedProcess:
    """Run the repo CLI (``python -m atdd ...``) from a real checkout.

    ``env`` overlays extra environment variables on the inherited environment —
    used by the generate-path smokes to pin a temp ``ATDD_CONTROL_ROOT`` and a
    stubbed ``gh`` (#1272 made ``atdd author issue`` publish store-first, so the
    smoke runs hermetically rather than filing a real GitHub issue).
    """
    proc_env = None
    if env is not None:
        import os

        proc_env = {**os.environ, **env}
    return subprocess.run(
        [sys.executable, "-m", "atdd", *args],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        env=proc_env,
    )
