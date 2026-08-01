# URN: test:govern-lifecycle:R009-UNIT-001-workflow-names-only-the-token-its-permissions-describe
# Acceptance: acc:govern-lifecycle:R009-UNIT-001-workflow-names-only-the-token-its-permissions-describe
# WMBT: wmbt:govern-lifecycle:R009
# Phase: RED
# Layer: backend.integration
# Assertion: structural
"""
Coach validator: assert the atdd-auto-phase GitHub Actions workflow exists.

Issue #355: PR-merge → phase advance is enforced by
.github/workflows/atdd-auto-phase.yml. If the file is removed or stops
dispatching `atdd auto-phase`, hand-typed transitions creep back in. This
validator hard-fails CI when the workflow file regresses.

Run: atdd validate coach
"""

from pathlib import Path

import pytest
import yaml

from atdd.coach.utils.repo import find_repo_root

# Toolkit dogfood: asserts on toolkit-only repo content (#1475).
pytestmark = [pytest.mark.platform]

REPO_ROOT = find_repo_root()
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "atdd-auto-phase.yml"
TEMPLATE_PATH = (
    REPO_ROOT
    / "src" / "atdd" / "coach" / "templates" / "workflows" / "atdd-auto-phase.yml"
)


def _load_workflow() -> dict:
    if not WORKFLOW_PATH.exists():
        pytest.fail(
            f"Missing workflow file: {WORKFLOW_PATH.relative_to(REPO_ROOT)}. "
            "Issue #355 requires this workflow to auto-transition issue "
            "phase on PR merge."
        )
    return yaml.safe_load(WORKFLOW_PATH.read_text()) or {}


def _load_template() -> dict:
    if not TEMPLATE_PATH.exists():
        pytest.skip(
            f"Template not present at {TEMPLATE_PATH.relative_to(REPO_ROOT)} "
            "(consumer repo without toolkit source) — deployed-file checks "
            "still apply."
        )
    return yaml.safe_load(TEMPLATE_PATH.read_text()) or {}


def _job_permissions(wf: dict) -> dict:
    """Extract the auto-phase job's `permissions:` block."""
    return ((wf.get("jobs") or {}).get("auto-phase") or {}).get("permissions") or {}


def test_auto_phase_workflow_file_exists():
    """File must exist at the canonical path."""
    assert WORKFLOW_PATH.exists(), (
        f"{WORKFLOW_PATH.relative_to(REPO_ROOT)} is required (issue #355)."
    )


def test_auto_phase_workflow_triggers_on_pr_close():
    """Must fire on `pull_request: closed`."""
    wf = _load_workflow()
    # PyYAML parses the bare key `on` as Python True; tolerate both.
    triggers = wf.get("on") or wf.get(True) or {}
    pr_trigger = triggers.get("pull_request") or {}
    types = pr_trigger.get("types") or []
    assert "closed" in types, (
        "atdd-auto-phase.yml must trigger on pull_request: closed; "
        f"found types={types!r}"
    )


def test_auto_phase_workflow_can_be_re_driven_for_a_merged_pr():
    """Issue #1611: an already-merged PR must be re-runnable at current main.

    ``gh run rerun`` replays a run at the commit it ran on, so a fix to a COMPLETE
    gate could never be exercised on the PRs that fix was written for — the run
    would install the same broken code that failed the first time. A manual
    dispatch taking a PR number runs the same command at current main instead.
    """
    wf = _load_workflow()
    # PyYAML parses the bare key `on` as Python True; tolerate both.
    triggers = wf.get("on") or wf.get(True) or {}
    assert "workflow_dispatch" in triggers, (
        "atdd-auto-phase.yml must offer `workflow_dispatch` so a merged PR can be "
        f"re-driven without --force. Found triggers={sorted(triggers)!r}."
    )
    inputs = (triggers.get("workflow_dispatch") or {}).get("inputs") or {}
    assert "pr_number" in inputs, (
        "the `workflow_dispatch` trigger must take a `pr_number` input naming the "
        f"merged PR to re-run. Found inputs={sorted(inputs)!r}."
    )

    job = (wf.get("jobs") or {}).get("auto-phase") or {}
    assert "workflow_dispatch" in str(job.get("if") or ""), (
        "the auto-phase job's `if:` gates on `pull_request.merged`, which is empty "
        "on a manual dispatch — it must admit `workflow_dispatch` too."
    )
    assert "inputs.pr_number" in WORKFLOW_PATH.read_text(), (
        "the dispatched PR number must reach the `atdd auto-phase` step."
    )


def test_auto_phase_workflow_gated_on_merged():
    """Must guard with `merged == true` so unmerged closes don't transition."""
    content = WORKFLOW_PATH.read_text()
    assert "merged == true" in content, (
        "atdd-auto-phase.yml must gate the job on "
        "`github.event.pull_request.merged == true`."
    )


def test_auto_phase_workflow_invokes_atdd_auto_phase():
    """Must dispatch to `atdd auto-phase` so the state-machine logic runs."""
    content = WORKFLOW_PATH.read_text()
    assert "auto-phase" in content, (
        "atdd-auto-phase.yml must invoke `atdd auto-phase` (or "
        "`python -m atdd.cli auto-phase`) to perform the transition."
    )


#: The only credential the job may name. #1621: `secrets.PROJECT_TOKEN ||
#: secrets.GITHUB_TOKEN` was written as a fallback and behaves as a preference —
#: with the secret present, `||` short-circuits and GITHUB_TOKEN is never reached.
_GITHUB_TOKEN_EXPR = "${{ secrets.GITHUB_TOKEN }}"


def _job_env(wf: dict) -> dict:
    """Extract the `env:` block from the auto-phase job's `Run atdd auto-phase` step."""
    job = (wf.get("jobs") or {}).get("auto-phase") or {}
    for step in job.get("steps") or []:
        if "auto-phase" in (step.get("name") or "").lower():
            return step.get("env") or {}
    return {}


def test_auto_phase_workflow_does_not_request_projects_write():
    """Issue #404: `permissions:` must NOT declare `projects: write`.

    GITHUB_TOKEN cannot grant the account-level Projects scope, so declaring
    `projects: write` caused GitHub to reject the workflow at preflight on
    every run (0-second 'workflow file issue' failure). The fix dropped the
    permission and moved full ProjectV2 sync to an opt-in PROJECT_TOKEN PAT;
    the GH_TOKEN fallback expression silently degrades to label-only sync
    when no PAT is present.
    """
    perms = _job_permissions(_load_workflow())
    assert "projects" not in perms, (
        "atdd-auto-phase.yml `permissions:` MUST NOT declare any `projects:` "
        "scope — GITHUB_TOKEN cannot satisfy it and preflight rejects the "
        f"workflow. Found permissions={perms!r}. Issue #404."
    )


def test_auto_phase_workflow_template_does_not_request_projects_write():
    """Issue #404: the shipped template must not declare `projects: write` either.

    Otherwise `atdd init --force` would regress every consumer repo back to
    the broken preflight shape.
    """
    perms = _job_permissions(_load_template())
    assert "projects" not in perms, (
        "src/atdd/coach/templates/workflows/atdd-auto-phase.yml "
        "`permissions:` MUST NOT declare any `projects:` scope. "
        f"Found permissions={perms!r}. Issue #404."
    )


def test_auto_phase_workflow_uses_the_token_its_permissions_are_declared_for():
    """Issue #1621: `GH_TOKEN` must be GITHUB_TOKEN — the token that carries issues:write.

    This assertion is the inverse of the one it replaces, and deliberately so.
    #404 introduced `${{ secrets.PROJECT_TOKEN || secrets.GITHUB_TOKEN }}` because
    GITHUB_TOKEN cannot grant the account-level Projects scope. #1051 then
    decommissioned Projects v2, so nothing needs that scope any more — but the
    expression outlived its reason, and `||` short-circuits: with PROJECT_TOKEN set
    as a repo secret, GITHUB_TOKEN is *never* reached.

    The result was that every label write from the workflow failed with
    ``Resource not accessible by personal access token (removeLabelsFromLabelable)``
    while the job's own ``permissions: issues: write`` granted exactly that
    capability — to the token it never used.
    """
    env = _job_env(_load_workflow())
    gh_token = env.get("GH_TOKEN", "")
    assert gh_token == _GITHUB_TOKEN_EXPR, (
        f"atdd-auto-phase.yml `GH_TOKEN` must be '{_GITHUB_TOKEN_EXPR}'. The job "
        "declares `permissions: issues: write`, which applies to GITHUB_TOKEN and "
        "to nothing else — naming any other credential hands the label write to a "
        f"token that was never granted it. Found GH_TOKEN={gh_token!r}. Issue #1621."
    )
    assert "PROJECT_TOKEN" not in gh_token, (
        "atdd-auto-phase.yml still consults PROJECT_TOKEN. The PAT existed only "
        "for the ProjectV2 Status sync that #1051 decommissioned; consulting it "
        "shadows the correctly-permissioned token. Issue #1621."
    )


def test_auto_phase_workflow_template_uses_the_same_token():
    """Issue #1621: the shipped template must not seed consumers with the same trap.

    The template is how the defect spreads: any consumer that followed #404 and
    created a PROJECT_TOKEN gets a PAT silently preferred over the token their
    `permissions:` block actually describes.
    """
    env = _job_env(_load_template())
    gh_token = env.get("GH_TOKEN", "")
    assert gh_token == _GITHUB_TOKEN_EXPR, (
        "src/atdd/coach/templates/workflows/atdd-auto-phase.yml `GH_TOKEN` must be "
        f"'{_GITHUB_TOKEN_EXPR}'. Found GH_TOKEN={gh_token!r}. Issue #1621."
    )


def test_auto_phase_workflow_carries_no_stale_projectv2_rationale():
    """Issue #1621: the comment justifying the PAT must go with the PAT.

    The rationale above `permissions:` still told the next reader that the PAT
    exists for "full ProjectV2 Status sync" — a code path removed in #1051. That
    comment is why the expression survived two investigations: it read as a
    deliberate, still-load-bearing choice.
    """
    for path in (WORKFLOW_PATH, TEMPLATE_PATH):
        if not path.exists():
            continue
        content = path.read_text()
        assert "PROJECT_TOKEN" not in content, (
            f"{path.name} still mentions PROJECT_TOKEN. The credential is "
            "vestigial (#1051 removed ProjectV2); leaving the name in the file "
            "invites it back. Issue #1621."
        )
        assert "ProjectV2 Status sync" not in content, (
            f"{path.name} still describes ProjectV2 Status sync as a live reason. "
            "Issue #1621."
        )


#: The expression itself, as an operator would copy it out of a doc. Split so
#: this file's own assertion text cannot be what the scan trips over.
_FALLBACK_EXPR_FRAGMENT = "secrets.PROJECT_TOKEN" + " || " + "secrets.GITHUB_TOKEN"


def _prose_that_could_re_seed_the_fallback():
    """Every shipped file an operator or an agent would take instruction from.

    Two surfaces, not one. `docs/` is where the human looks;
    `src/atdd/*/conventions/*.yaml` is where the AGENT looks — CLAUDE.md's
    canonical-source pointers send it there by name, which makes a convention
    the more authoritative of the two and the worse place to leave the
    expression lying around.
    """
    docs = (REPO_ROOT / "docs").rglob("*.md")
    conventions = (REPO_ROOT / "src" / "atdd").glob("*/conventions/**/*.yaml")
    return sorted(set(docs) | set(conventions))


def test_no_shipped_doc_instructs_an_operator_to_re_seed_the_fallback():
    """Issue #1621: removing the expression is not enough while prose still teaches it.

    `docs/operator-projects-v2-token.md` survived #1051 and went on telling
    operators to write

        GH_TOKEN: ${{ secrets.PROJECT_TOKEN || secrets.GITHUB_TOKEN }}

    citing *this validator* as the thing that asserted the pattern — which it
    did, until #1621 inverted it. Prose that contradicts the shipped guard is
    how the defect comes back after the fix: the next operator follows the
    written instruction, not the test.

    #1051's own plan called for deleting that doc (see the E053 WMBT statement
    and `decommission_projects_v2_board_sync.yaml`); the deletion was never
    made. This assertion is the ratchet that keeps it deleted.

    The scan covers conventions as well as docs because deleting the doc alone
    left the expression alive in
    `issue.convention.yaml::status.auto_transition_on_merge.projects_access_fallback`
    — a block that also declared `enabled: true` for a degraded mode whose
    trigger string this same issue reclassified into a hard refusal. A
    docs-only ratchet could not see it, so the success criterion it backed
    ("no shipped doc instructs an operator to write the `||` expression") was
    asserted without being true.
    """
    candidates = _prose_that_could_re_seed_the_fallback()
    if not candidates:
        pytest.skip("no shipped docs or conventions (consumer repo)")

    offenders = [
        path.relative_to(REPO_ROOT)
        for path in candidates
        if _FALLBACK_EXPR_FRAGMENT in path.read_text()
    ]
    assert not offenders, (
        "These shipped files still instruct an operator to write "
        f"`{_FALLBACK_EXPR_FRAGMENT}` as GH_TOKEN: {offenders}. `||` is a "
        "preference, not a fallback — with PROJECT_TOKEN set as a repo secret "
        "GITHUB_TOKEN is never reached, and the job's `permissions: issues: "
        "write` applies to GITHUB_TOKEN alone. Every label write then fails "
        "with `Resource not accessible by personal access token`. Issue #1621."
    )
