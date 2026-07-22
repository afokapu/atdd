# URN: test:govern-lifecycle:R005-UNIT-001-no-raw-phase-label-writers
# Acceptance: acc:govern-lifecycle:R005-UNIT-001-no-raw-phase-label-writers
# WMBT: wmbt:govern-lifecycle:R005
# Phase: RED
# Layer: backend.domain
# Assertion: behavioral
"""R005-UNIT-001 — nothing outside ``IssueManager.update`` writes an ``atdd:<PHASE>``
label, and the guard that says so is demonstrably capable of failing.

The second half matters as much as the first. A guard that has only ever been
run against a clean tree has not been shown to work — it has been shown to be
quiet, which is also what a stub does. So this drives the same scanner over a
verbatim copy of the step deleted from ``post-merge-lifecycle.yml`` and requires
it to go red, including on the interpolated ``atdd:${PHASE}`` removal loop that a
literal-only match would sail past.

Issue #1452.
"""
from __future__ import annotations

import pytest

from atdd.coach.validators.test_phase_label_projection_only import (
    AUTHORITATIVE_WRITER,
    _scanned_sources,
    scan_for_raw_phase_label_writes,
)

pytestmark = [pytest.mark.coach]


# The step as it stood in .github/workflows/post-merge-lifecycle.yml before #1452.
_DELETED_STEP = """
      - name: Swap labels to atdd:COMPLETE
        if: steps.extract.outputs.found == 'true'
        run: |
          LABELS=$(gh issue view "$ISSUE" --repo "$REPO" --json labels --jq '.labels[].name')
          for PHASE in INIT PLANNED RED GREEN SMOKE REFACTOR BLOCKED; do
            if echo "$LABELS" | grep -qx "atdd:${PHASE}"; then
              gh issue edit "$ISSUE" --repo "$REPO" --remove-label "atdd:${PHASE}"
            fi
          done
          gh issue edit "$ISSUE" --repo "$REPO" --add-label "atdd:COMPLETE"
"""


def test_real_repo_has_no_raw_phase_label_writer():
    """The whole repo — workflows, templates, scripts, modules — is clean."""
    violations = scan_for_raw_phase_label_writes(_scanned_sources())
    assert violations == [], (
        "A raw atdd:<PHASE> label writer exists outside "
        f"{AUTHORITATIVE_WRITER}. The label is a projection of objects.state; "
        "authoring it independently is what stranded 236 of 421 issues. "
        "Sites: " + "; ".join(f"{v.location} — {v.detail}" for v in violations)
    )


def test_guard_goes_red_on_the_verbatim_deleted_step():
    """Fault injection: replant the real step, and the guard must fail."""
    violations = scan_for_raw_phase_label_writes(
        {".github/workflows/post-merge-lifecycle.yml": _DELETED_STEP}
    )
    assert len(violations) == 2, (
        "Replanting the deleted label-swap step must produce a violation for "
        "BOTH the interpolated remove and the literal add. A guard that misses "
        "either half would have let #1434's regrowth through again. Got: "
        f"{[v.location for v in violations]}"
    )
    assert all(
        v.rule_id == "coach.phase-label.projection-only" for v in violations
    )


def test_guard_goes_red_on_an_underscore_prefixed_python_writer():
    """The second real writer #1452 found was a module-level `_gh_add_label`.

    It carries no leading dot, so a `\\.add_label\\(` pattern misses it entirely.
    That is precisely how a raw writer survives a guard that looks correct.
    """
    violations = scan_for_raw_phase_label_writes(
        {
            "src/atdd/coach/commands/coach.py": (
                '    _gh_add_label(issue_number, [f"atdd:{new_phase.value}"])\n'
            )
        }
    )
    assert len(violations) == 1, (
        "An underscore-prefixed label-write shim must be caught — renaming the "
        f"wrapper must not be an escape hatch. Got: {violations}"
    )
