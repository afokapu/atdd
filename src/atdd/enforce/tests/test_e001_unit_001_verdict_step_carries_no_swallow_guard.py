# URN: test:enforce-conventions-ci:E001-UNIT-001-verdict-step-carries-no-swallow-guard
# Acceptance: acc:enforce-conventions-ci:E001-UNIT-001-verdict-step-carries-no-swallow-guard
# WMBT: wmbt:enforce-conventions-ci:E001
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""GREEN Test for acc:enforce-conventions-ci:E001-UNIT-001-verdict-step-carries-no-swallow-guard.

The `atdd enforce` VERDICT step is blocking only when NEITHER guard that swallows a
non-zero exit is present. There are exactly two, and each is independently fatal:

    continue-on-error: true     the step fails, the JOB still succeeds
    ... || true                 the command fails, the STEP still succeeds

Read over synthetic workflows, both guards are detected, and a step carrying
neither is reported blocking. This is the predicate the #1427 core-succession guard
also reads (``path_b_is_blocking``) — one definition, two consumers.
"""
from __future__ import annotations

from pathlib import Path

from atdd.enforce.ci_gate import path_b_is_blocking

_VERDICT_RUN = "PYTHONPATH=src python3 -m atdd enforce --repo-root . --paths src/atdd"


def _write_workflow(root: Path, verdict_step: str) -> Path:
    wf = root / ".github" / "workflows" / "atdd-validate.yml"
    wf.parent.mkdir(parents=True, exist_ok=True)
    wf.write_text(
        "name: ATDD Validate\n"
        "on: [push]\n"
        "jobs:\n"
        "  enforce-extensions:\n"
        "    runs-on: ubuntu-latest\n"
        "    steps:\n"
        "      - name: Verify extension substrate (blocking)\n"
        "        run: python3 -m atdd enforce --verify-substrate --repo-root .\n"
        f"{verdict_step}",
        encoding="utf-8",
    )
    return wf


def test_continue_on_error_is_detected_as_not_blocking(tmp_path: Path) -> None:
    _write_workflow(
        tmp_path,
        "      - name: Enforce extension conventions\n"
        "        continue-on-error: true\n"
        f"        run: {_VERDICT_RUN}\n",
    )

    assert path_b_is_blocking(tmp_path) is False, (
        "`continue-on-error: true` swallows the step's failure — the job still "
        "succeeds, so the verdict is NOT blocking"
    )


def test_or_true_is_detected_as_not_blocking(tmp_path: Path) -> None:
    _write_workflow(
        tmp_path,
        "      - name: Enforce extension conventions\n"
        f"        run: {_VERDICT_RUN} || true\n",
    )

    assert path_b_is_blocking(tmp_path) is False, (
        "`|| true` swallows the command's non-zero exit — the step still succeeds, "
        "so the verdict is NOT blocking"
    )


def test_a_step_carrying_neither_guard_is_blocking(tmp_path: Path) -> None:
    _write_workflow(
        tmp_path,
        "      - name: Enforce extension conventions (BLOCKING)\n"
        f"        run: {_VERDICT_RUN} --ratchet .atdd/enforce-ratchet.yaml\n",
    )

    assert path_b_is_blocking(tmp_path) is True


def test_an_absent_workflow_is_not_blocking(tmp_path: Path) -> None:
    # Fail CLOSED: an absent gate is not a gate. Reporting True here would let the
    # succession guard believe a rule is enforced when nothing enforces it.
    assert path_b_is_blocking(tmp_path) is False


def test_the_verify_substrate_step_is_not_mistaken_for_the_verdict(tmp_path: Path) -> None:
    # The job runs `atdd enforce --verify-substrate` too. That guard step is NOT the
    # convention verdict; a reader that matched it would report the job blocking on
    # the strength of the wrong step. Here the real verdict step IS advisory, so a
    # correct reader must still say False.
    _write_workflow(
        tmp_path,
        "      - name: Enforce extension conventions\n"
        "        continue-on-error: true\n"
        f"        run: {_VERDICT_RUN}\n",
    )

    assert path_b_is_blocking(tmp_path) is False
