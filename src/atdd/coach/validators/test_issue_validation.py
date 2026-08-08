"""
Issue validation against GitHub Issues and Project v2 fields.

Purpose: Validate GitHub Issues before implementation starts.
Convention: src/atdd/coach/conventions/issue.convention.yaml

E008: Train enforcement validators (SPEC-SESSION-VAL-0050 to 0051):
- Issues must have a non-empty Train field after PLANNED phase
- Train field must reference a valid train_id from _trains.yaml

E010: Body section validator (SPEC-SESSION-VAL-0060):
- Issues should have all 11 structured sections from PARENT-ISSUE-TEMPLATE.md
- Soft check (warning) for pre-E010 issues

E011: Branch naming validator (SPEC-SESSION-VAL-0070):
- Issues past PLANNED must have a Branch field matching an allowed prefix
- Branch = worktree (every branch is created as a git worktree)

E012: State Store consistency validator (SPEC-SESSION-VAL-0080):
- Every open GitHub issue with atdd-issue label must resolve to a work item
  in the State Store via its github external_ref (provider github / issue)
- #1203 Phase 2: the State Store is authoritative for the work-item lifecycle;
  the manifest is a projection. The reader auto-imports the manifest into the
  store on first read, so this subsumes the prior manifest-shape check while
  asserting the authoritative source.
- Detects issues created directly via `gh issue create` or the GitHub UI
  instead of through `atdd issue <slug>`

Run: atdd validate coach
"""
import re
import warnings as w
import pytest
import yaml

from atdd.coach.utils.repo import find_repo_root

pytestmark = [pytest.mark.platform, pytest.mark.github_api]

# ============================================================================
# Configuration
# ============================================================================

REPO_ROOT = find_repo_root()


# ============================================================================
# E008: Issue Train Enforcement
# ============================================================================
#
# SPEC-SESSION-VAL-0050 / 0051 USED TO LIVE HERE as two validators reading the
# "ATDD Train" custom field off the Projects v2 board. #1051 decommissioned the
# board and #1761 removed the last of its read paths, this pair included.
#
# The enforcement did not go with them. `IssueManager._gate_train_required`
# (coach/commands/issue.py) applies the same rule — a train is required past
# PLANNED for implementation-type issues, and its value must resolve in
# plan/_trains.yaml — reading the local manifest mirror at transition time,
# which is where the lineage actually lives. That gate blocks the transition;
# these validators could only report after the fact, and once the board was
# gone they could only skip.


# ============================================================================
# E010: Body Section Validation (GitHub Issues)
# ============================================================================

PARENT_ISSUE_TEMPLATE = (
    REPO_ROOT / "src/atdd/coach/templates/PARENT-ISSUE-TEMPLATE.md"
)


def load_required_sections():
    """
    Parse PARENT-ISSUE-TEMPLATE.md to derive the list of required H2 sections.

    This is the single source of truth — updating the template file
    automatically updates what both the E010 validator and the CLI
    `atdd issue <N> --check` enforce.

    Returns: list of required H2 headings (e.g. ["## Issue Metadata", ...])
    """
    if not PARENT_ISSUE_TEMPLATE.exists():
        return []
    sections = []
    for line in PARENT_ISSUE_TEMPLATE.read_text().splitlines():
        if line.startswith("## ") and not line.startswith("### "):
            sections.append(line.strip())
    return sections


def check_body_sections(body):
    """
    Reusable compliance check — callable from CLI (`atdd issue <N> --check`)
    and from the E010 validator.

    Returns: list of missing section headings (empty list = compliant).
    """
    required = load_required_sections()
    body = body or ""
    return [s for s in required if s not in body]


def test_issue_body_has_required_sections(github_issues):
    """
    SPEC-SESSION-VAL-0060: Issue body should contain all structured sections

    Given: Open issues in the GitHub Project (label: atdd-issue)
    When: Checking the issue body for required H2 headings
    Then: All sections derived from PARENT-ISSUE-TEMPLATE.md should be present
          Pre-E010 issues emit warnings instead of hard failures

    E010 acceptance criteria: `atdd validate coach` warns if issue body is missing sections.

    Template is the single source of truth — parsed at runtime from
    src/atdd/coach/templates/PARENT-ISSUE-TEMPLATE.md. Updating the
    template automatically updates this validator.
    """
    if not load_required_sections():
        pytest.skip("PARENT-ISSUE-TEMPLATE.md not found")

    incomplete = []
    for issue in github_issues:
        num = issue["number"]
        missing = check_body_sections(issue.get("body", ""))
        if missing:
            incomplete.append(
                f"#{num}: missing {len(missing)} section(s): {', '.join(missing)}"
            )

    if incomplete:
        w.warn(
            f"Issues with incomplete body sections ({len(incomplete)}):\n  "
            + "\n  ".join(incomplete)
            + "\n\nHint: Re-author the body with `atdd author issue --revise <N>` for a full-structure body.",
            category=UserWarning,
            stacklevel=1,
        )


# ============================================================================
# E011: Branch Naming Validation (GitHub Issues)
# ============================================================================

ALLOWED_BRANCH_PREFIXES = ("feat/", "fix/", "refactor/", "chore/", "docs/", "devops/")

# Active statuses where branch must be set (excludes terminal COMPLETE/OBSOLETE)
_ACTIVE_IMPL_STATUSES = {"RED", "GREEN", "SMOKE", "REFACTOR"}

_BRANCH_RE = re.compile(r"\| Branch \| (.+?) \|")


def test_issue_branch_follows_worktree_convention(github_issues):
    """
    SPEC-SESSION-VAL-0070: Branch field must use an allowed worktree prefix

    Given: Open issues in the GitHub Project (label: atdd-issue)
    When: Checking the Branch field in Issue Metadata table
    Then: Issues past PLANNED must have Branch matching {prefix}/{slug}
          Issues at INIT/PLANNED with TBD get a warning

    Every branch is a git worktree. Allowed prefixes: feat/, fix/, refactor/,
    chore/, docs/, devops/
    """
    violations = []
    warnings_list = []

    for issue in github_issues:
        num = issue["number"]
        body = issue.get("body", "") or ""

        match = _BRANCH_RE.search(body)
        if not match:
            continue

        branch = match.group(1).strip().strip("`")
        # Strip HTML comment hint from template
        if "<!--" in branch:
            branch = branch[:branch.index("<!--")].strip()

        labels = [l["name"] for l in issue.get("labels", [])]
        status = "UNKNOWN"
        for l in labels:
            if l.startswith("atdd:"):
                status = l.split(":")[1].upper()

        is_tbd = not branch or branch.upper() == "TBD"

        if is_tbd and status in _ACTIVE_IMPL_STATUSES:
            violations.append(
                f"#{num} (status={status}): Branch is TBD — "
                f"must be set before implementation"
            )
        elif is_tbd:
            continue  # TBD at INIT/PLANNED is fine
        elif not any(branch.startswith(p) for p in ALLOWED_BRANCH_PREFIXES):
            violations.append(
                f"#{num}: Branch='{branch}' does not start with an allowed "
                f"prefix: {', '.join(ALLOWED_BRANCH_PREFIXES)}"
            )

    assert not violations, (
        f"\nBranch field must use a worktree prefix "
        f"({', '.join(ALLOWED_BRANCH_PREFIXES)}).\n"
        f"Each branch = a git worktree. "
        f"Example: git worktree add ../feat-my-feature -b feat/my-feature\n\n"
        f"Violations ({len(violations)}):\n  " + "\n  ".join(violations)
    )


# ============================================================================
# E012: State Store Consistency Validation (GitHub Issues vs the State Store)
# ============================================================================


def _store_resolved_issue_numbers(candidate_numbers):
    """Return which of *candidate_numbers* resolve to a work item in the store.

    #1203 Phase 2: the State Store is authoritative for the work-item lifecycle.
    Each GitHub issue number is resolved through the ``github`` external_ref
    projection (the same bridge the lifecycle command writes). The reader
    auto-imports the manifest into the store on first read, so a freshly-cloned
    repo still resolves issues created through ``atdd issue <slug>``. Returns the
    empty set if the store layer is unavailable so the caller degrades to "all
    unresolved" rather than crashing the validator.
    """
    try:
        from atdd.state.work_item_reader import WorkItemReader

        resolved = set()
        with WorkItemReader(control_root=REPO_ROOT) as reader:
            for num in candidate_numbers:
                if reader.get(num) is not None:
                    resolved.add(num)
        return resolved
    except Exception:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-11-19
        return set()


def test_github_issues_registered_in_state_store(github_issues):
    """
    SPEC-SESSION-VAL-0080: GitHub issues must resolve in the State Store

    Given: Open issues on GitHub with the atdd-issue label
    When: Resolving each issue number through the State Store github external_ref
    Then: Every issue number must resolve to a stored work item

    E012 acceptance criteria: `atdd validate coach` warns when an issue exists on
    GitHub but has no work item in the State Store (the authoritative source as of
    #1203 Phase 2; the manifest is a projection). This catches direct
    `gh issue create` or GitHub UI usage that bypasses `atdd issue <slug>`,
    WMBT sub-issue generation, and external-ref linkage.
    """
    numbers = [issue["number"] for issue in github_issues]
    resolved = _store_resolved_issue_numbers(numbers)

    unregistered = []
    for issue in github_issues:
        num = issue["number"]
        if num not in resolved:
            title = issue.get("title", "(no title)")
            unregistered.append(f"#{num}: {title}")

    if unregistered:
        w.warn(
            f"Issues on GitHub not resolvable in the State Store "
            f"({len(unregistered)}):\n  "
            + "\n  ".join(unregistered)
            + "\n\nThese issues were likely created outside `atdd issue <slug>`."
            + "\nFix: Re-create via `atdd issue <slug>` or run"
            + " `atdd state import-manifest` to backfill the store.",
            category=UserWarning,
            stacklevel=1,
        )
