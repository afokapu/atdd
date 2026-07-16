# URN: test:enforce-conventions-ci:E001-UNIT-002-blocking-job-is-required-by-the-gate-fan-in
# Acceptance: acc:enforce-conventions-ci:E001-UNIT-002-blocking-job-is-required-by-the-gate-fan-in
# WMBT: wmbt:enforce-conventions-ci:E001
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""GREEN Test for acc:enforce-conventions-ci:E001-UNIT-002-blocking-job-is-required-by-the-gate-fan-in.

A blocking verdict step only blocks the MERGE if the job carrying it is DEMANDED by
the gate. Two halves, each independently droppable, so each is asserted:

  * ``validate-gate`` lists ``enforce-extensions`` in ``needs``; and
  * it actually INSPECTS that job's result.

The second half is the subtle one: ``validate-gate`` runs ``if: always()``, so a
failed dependency does NOT fail it by itself — only the explicit result loop does.
A job sitting in ``needs`` whose result is never checked is decorative, and a reader
that only looked at ``needs`` would report a gate that cannot block as if it could.
"""
from __future__ import annotations

from pathlib import Path

from atdd.enforce.ci_gate import enforce_job_is_required, verdict_uses_ratchet

_RESULT_CHECK = (
    '          for result in "enforce-extensions:${{ needs.enforce-extensions.result }}"; do\n'
    '            status="${result##*:}"\n'
    '            if [ "$status" != "success" ] && [ "$status" != "skipped" ]; then exit 1; fi\n'
    "          done\n"
)


def _write_workflow(root: Path, *, needs: list[str], check_result: bool,
                    verdict_run: str = "python3 -m atdd enforce --paths src/atdd "
                                       "--ratchet .atdd/enforce-ratchet.yaml") -> Path:
    wf = root / ".github" / "workflows" / "atdd-validate.yml"
    wf.parent.mkdir(parents=True, exist_ok=True)
    needs_yaml = ", ".join(needs)
    body = (
        "name: ATDD Validate\n"
        "on: [push]\n"
        "jobs:\n"
        "  enforce-extensions:\n"
        "    runs-on: ubuntu-latest\n"
        "    steps:\n"
        "      - name: Enforce extension conventions\n"
        f"        run: {verdict_run}\n"
        "  validate-gate:\n"
        f"    needs: [{needs_yaml}]\n"
        "    runs-on: ubuntu-latest\n"
        "    if: always()\n"
        "    steps:\n"
        "      - name: Check results\n"
        "        run: |\n"
        + (_RESULT_CHECK if check_result else '          echo "all good"\n')
    )
    wf.write_text(body, encoding="utf-8")
    return wf


def test_job_in_needs_and_result_checked_is_required(tmp_path: Path) -> None:
    _write_workflow(tmp_path, needs=["validate-planner", "enforce-extensions"], check_result=True)

    assert enforce_job_is_required(tmp_path) is True


def test_a_gate_that_omits_the_job_from_needs_does_not_require_it(tmp_path: Path) -> None:
    # The omission must not pass unnoticed: with the job absent from the fan-in, a
    # failing enforce run never reaches the required check at all.
    _write_workflow(tmp_path, needs=["validate-planner"], check_result=True)

    assert enforce_job_is_required(tmp_path) is False


def test_a_job_in_needs_whose_result_is_never_checked_is_decorative(tmp_path: Path) -> None:
    # validate-gate is `if: always()`, so depending on a job without inspecting its
    # result does NOT make it blocking — this is the trap the reader must not fall into.
    _write_workflow(tmp_path, needs=["validate-planner", "enforce-extensions"], check_result=False)

    assert enforce_job_is_required(tmp_path) is False


def test_an_absent_workflow_requires_nothing(tmp_path: Path) -> None:
    assert enforce_job_is_required(tmp_path) is False


def test_a_blocking_verdict_without_the_ratchet_is_flagged(tmp_path: Path) -> None:
    # The flip and the baseline are ONE change: a blocking step with no ratchet reds
    # the build on the repository's pre-existing debt.
    _write_workflow(
        tmp_path,
        needs=["enforce-extensions"],
        check_result=True,
        verdict_run="python3 -m atdd enforce --paths src/atdd",
    )

    assert verdict_uses_ratchet(tmp_path) is False


def test_a_verdict_step_invoking_the_ratchet_is_detected(tmp_path: Path) -> None:
    _write_workflow(tmp_path, needs=["enforce-extensions"], check_result=True)

    assert verdict_uses_ratchet(tmp_path) is True
