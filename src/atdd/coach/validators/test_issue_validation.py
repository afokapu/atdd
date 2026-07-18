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
# E008: Issue Train Enforcement (GitHub Issues)
# ============================================================================


def _load_valid_train_ids():
    """Load all valid train IDs from plan/_trains.yaml and plan/_trains/*.yaml."""
    plan_dir = REPO_ROOT / "plan"
    trains_file = plan_dir / "_trains.yaml"
    valid_ids = set()

    if trains_file.exists():
        with open(trains_file) as f:
            data = yaml.safe_load(f) or {}
        for theme_key, categories in data.get("trains", {}).items():
            if isinstance(categories, dict):
                for cat_key, trains_list in categories.items():
                    if isinstance(trains_list, list):
                        for t in trains_list:
                            tid = t.get("train_id", "")
                            if tid:
                                valid_ids.add(tid)

    trains_dir = plan_dir / "_trains"
    if trains_dir.exists():
        for f in trains_dir.glob("*.yaml"):
            valid_ids.add(f.stem)

    return valid_ids


# Post-PLANNED phases where Train field is required
_POST_PLANNED_STATUSES = {"RED", "GREEN", "SMOKE", "REFACTOR", "COMPLETE"}


def test_issues_have_train_field(github_issues, github_project_fields, github_project_items):
    """
    SPEC-SESSION-VAL-0050: Issues must have a non-empty Train field

    Given: Open issues in the GitHub Project (label: atdd-issue)
    When: Checking the Train custom field value
    Then: Issues past PLANNED phase must have Train != TBD and != blank
          Issues at PLANNED phase get a warning if Train is TBD

    E008 acceptance criteria: `atdd validate coach` fails if issue has no train assignment.
    """
    if "ATDD Train" not in github_project_fields:
        pytest.skip("Train field not configured in Project")

    violations = []
    warnings_list = []

    for issue in github_issues:
        num = issue["number"]
        item = github_project_items.get(num)
        if not item:
            continue

        values = item["fields"]
        train_value = (values.get("ATDD Train") or "").strip()
        status_value = (values.get("ATDD Status") or "UNKNOWN").strip().upper()

        is_empty = not train_value or train_value.upper() == "TBD"

        if is_empty and status_value in _POST_PLANNED_STATUSES:
            violations.append(
                f"#{num} (status={status_value}): Train field is "
                f"{'TBD' if train_value.upper() == 'TBD' else 'empty'}"
            )
        elif is_empty and status_value == "PLANNED":
            warnings_list.append(
                f"#{num} (status=PLANNED): Train field is TBD — "
                f"required before transitioning past PLANNED"
            )

    if warnings_list:
        w.warn(
            f"Issue train assignment warnings ({len(warnings_list)}):\n  "
            + "\n  ".join(warnings_list),
            category=UserWarning,
            stacklevel=1,
        )

    assert not violations, (
        f"\nIssues past PLANNED must have a valid Train field (not TBD, not blank).\n"
        f"Fix: Run `atdd update <issue_number> --train <train_id>` "
        f'(e.g. "atdd update 467 --train 0001-self-compliance-validate"; '
        f"see plan/_trains.yaml::trains[].id for valid train ids).\n\n"
        f"Violations ({len(violations)}):\n  " + "\n  ".join(violations)
    )


def test_issue_train_references_valid_train_id(github_issues, github_project_fields, github_project_items):
    """
    SPEC-SESSION-VAL-0051: Issue Train field must reference a valid train_id

    Given: Issues with a non-empty Train field
    When: Cross-referencing against plan/_trains.yaml
    Then: The Train value matches a known train_id

    E008 acceptance criteria: Train value must reference a valid train_id from _trains.yaml.
    """
    valid_train_ids = _load_valid_train_ids()
    if not valid_train_ids:
        pytest.skip("No trains found in plan/_trains.yaml")

    if "ATDD Train" not in github_project_fields:
        pytest.skip("Train field not configured in Project")

    invalid = []

    for issue in github_issues:
        num = issue["number"]
        item = github_project_items.get(num)
        if not item:
            continue

        train_value = (item["fields"].get("ATDD Train") or "").strip()

        # Skip empty/TBD — handled by SPEC-SESSION-VAL-0050
        if not train_value or train_value.upper() == "TBD":
            continue

        if train_value not in valid_train_ids:
            invalid.append(
                f"#{num}: Train='{train_value}' not found in _trains.yaml"
            )

    assert not invalid, (
        f"\nIssue Train field values must reference valid train IDs from plan/_trains.yaml.\n"
        f"Valid train IDs: {', '.join(sorted(list(valid_train_ids)[:10]))}...\n\n"
        f"Invalid references ({len(invalid)}):\n  " + "\n  ".join(invalid)
    )


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
