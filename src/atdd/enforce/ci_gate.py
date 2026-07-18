# URN: component:enforce-conventions-ci:enforce-conventions-ci:ci_gate:backend:domain
# Runtime: python
# Purpose: Read the CI wiring that makes extension enforcement a REQUIRED check —
#          is the enforce job demanded by the validate-gate fan-in, and does its
#          verdict step run under the ratchet baseline?
"""Readers over the enforce job's CI wiring (#1428 E001).

A blocking verdict step only blocks the MERGE if the job carrying it is actually
DEMANDED by the gate. Both halves must hold, and each can be dropped
independently — so each is read, and asserted, separately:

  1. the verdict step is BLOCKING — neither ``continue-on-error: true`` nor
     ``|| true`` swallows its non-zero exit. That predicate already exists as
     :func:`atdd.enforce.registry.path_b_is_blocking` (the succession guard reads
     it to decide whether deleting a core node would silently strip enforcement),
     and is imported here rather than re-implemented — one definition of
     "blocking", read by both the guard and the gate;

  2. the job is REQUIRED — ``validate-gate`` lists it in ``needs`` AND inspects
     its result. A job in ``needs`` whose result is never checked is decorative:
     ``validate-gate`` runs ``if: always()``, so a failed dependency does NOT fail
     the gate by itself — only the explicit result loop does. Reading only ``needs``
     would therefore report a gate that cannot actually block as if it could;

  3. the verdict runs under the RATCHET (:mod:`atdd.enforce.ratchet`) — without it
     the blocking job reds on the 23 pre-existing failing rules and gets reverted.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import yaml

# One definition of "is the enforce verdict blocking?", shared with the #1427
# core-succession guard — the two must never be able to disagree.
from atdd.enforce.registry import path_b_is_blocking

__all__ = ["ENFORCE_JOB", "GATE_JOB", "enforce_job_is_required", "path_b_is_blocking",
           "verdict_uses_ratchet"]

_log = logging.getLogger(__name__)

#: The CI job that runs `atdd enforce` over the vendored substrate.
ENFORCE_JOB = "enforce-extensions"

#: The fan-in job whose success is the repository's required merge check.
GATE_JOB = "validate-gate"

_WORKFLOW = Path(".github") / "workflows" / "atdd-validate.yml"


def _load_workflow(repo_root: str | Path) -> Optional[dict]:
    path = Path(repo_root) / _WORKFLOW
    if not path.is_file():
        return None
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        _log.warning(
            "unreadable CI workflow — enforce gate treated as unwired",
            extra={"workflow": str(path), "error": str(exc)},
        )
        return None
    return data if isinstance(data, dict) else None


def _jobs(workflow: Optional[dict]) -> dict:
    jobs = workflow.get("jobs") if isinstance(workflow, dict) else None
    return jobs if isinstance(jobs, dict) else {}


def _verdict_steps(repo_root: str | Path) -> list[dict]:
    """Every ``enforce-extensions`` step running the VERDICT (not ``--verify-substrate``)."""
    job = _jobs(_load_workflow(repo_root)).get(ENFORCE_JOB)
    steps = job.get("steps") if isinstance(job, dict) else None
    if not isinstance(steps, list):
        return []
    return [
        step
        for step in steps
        if isinstance(step, dict)
        and "atdd enforce" in str(step.get("run") or "")
        and "--verify-substrate" not in str(step.get("run") or "")
    ]


def enforce_job_is_required(repo_root: str | Path) -> bool:
    """Whether ``validate-gate`` both NEEDS the enforce job and CHECKS its result.

    Fails closed: an absent workflow, gate job, or result check is not a required
    check. Both halves are required — see the module docstring on why ``needs``
    alone is decorative under ``if: always()``.
    """
    gate = _jobs(_load_workflow(repo_root)).get(GATE_JOB)
    if not isinstance(gate, dict):
        return False

    needs = gate.get("needs")
    needs = [needs] if isinstance(needs, str) else needs
    if not isinstance(needs, list) or ENFORCE_JOB not in needs:
        return False

    # The gate must actually INSPECT the job's result, not merely depend on it.
    steps = gate.get("steps") if isinstance(gate.get("steps"), list) else []
    checked = any(
        f"needs.{ENFORCE_JOB}.result" in str(step.get("run") or "")
        for step in steps
        if isinstance(step, dict)
    )
    return checked


def verdict_uses_ratchet(repo_root: str | Path) -> bool:
    """Whether the enforce VERDICT step judges against the recorded ratchet baseline.

    A blocking verdict step with no ratchet reds the build on the repository's
    pre-existing debt — the flip and the baseline are one change, not two.
    """
    return any("--ratchet" in str(step.get("run") or "") for step in _verdict_steps(repo_root))
