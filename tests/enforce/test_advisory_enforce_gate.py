"""Extension-enforcement gate wiring (#1359 activated it; #1428 made it REQUIRED).

Guards the MECHANISM against the vendored, committed substrate:

  * the canonical ``.atdd/binding.lock.yaml`` binds a real (non-no-op) coder/tester
    set, and train-interlocking is DEFERRED (#1361, blocked on #1292/#1345) — an
    unresolvable bind would break ``--verify-substrate`` and the gate;
  * ``atdd enforce --verify-substrate`` passes against the committed vendored tree
    (digest coherence — a real, blocking invariant);
  * CI wires ``atdd enforce`` and runs its VERDICT as a BLOCKING check — no
    ``continue-on-error``, no ``|| true`` — judged against the
    ``.atdd/enforce-ratchet.yaml`` debt register so the toolkit's pre-existing
    violations are held flat while any regression fails the build (#1428).

These are fast + dependency-light (no tree-sitter): the heavy convention verdict is
produced by the blocking CI step itself, visible in the CI log, not re-run here.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "atdd-validate.yml"
BINDING_LOCK = REPO_ROOT / ".atdd" / "binding.lock.yaml"


def _run_enforce(*args: str) -> subprocess.CompletedProcess:
    env = {
        **os.environ,
        "PYTHONDONTWRITEBYTECODE": "1",  # keep the vendored tree's digest stable
        "PYTHONPATH": str(REPO_ROOT / "src"),
    }
    return subprocess.run(
        [sys.executable, "-m", "atdd", "enforce", *args],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )


def _enforce_run_steps() -> list[tuple[str, dict, str]]:
    """Every workflow step whose ``run`` invokes ``atdd enforce`` — (job, step, run)."""
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8")) or {}
    steps: list[tuple[str, dict, str]] = []
    for job_name, job in (workflow.get("jobs") or {}).items():
        for step in job.get("steps", []) or []:
            run = step.get("run") or ""
            if "atdd enforce" in run:
                steps.append((job_name, step, run))
    return steps


def test_binding_lock_binds_runnable_set_including_train_interlocking():
    """GT-001: the canonical lock binds a non-empty coder/tester set, train-interlocking included."""
    assert BINDING_LOCK.is_file(), f"canonical binding.lock missing at {BINDING_LOCK}"
    lock = yaml.safe_load(BINDING_LOCK.read_text(encoding="utf-8")) or {}
    bound = [c for c in lock.get("conventions", []) if c.get("disposition") == "bound"]
    assert bound, "binding.lock has no bound conventions — enforce would be a silent no-op"
    ids = {c["convention_id"] for c in bound}
    assert any(i.startswith(("coder.", "tester.")) for i in ids), (
        f"expected coder/tester bound conventions, got: {sorted(ids)}"
    )
    # train-interlocking was held out while its two blockers stood: the composer
    # could not compose a list-valued realizes_convention, and an unresolvable
    # bound entry would have failed --verify-substrate. Both are now discharged —
    # the #1426 implementation fan-out composes the list form, and main ships the
    # extension enabled — so the rules bind, verify, and run. Pin that.
    assert any("interlocking" in i for i in ids), (
        "train-interlocking must be bound: the extension ships enabled and the "
        "fan-out composes its list-valued realizes_convention"
    )


def test_verify_substrate_passes_against_vendored_tree():
    """GT-002: the committed vendored substrate is digest-coherent (blocking invariant)."""
    proc = _run_enforce("--verify-substrate", "--repo-root", str(REPO_ROOT))
    assert proc.returncode == 0, (
        f"`atdd enforce --verify-substrate` FAILED (exit {proc.returncode}):\n"
        f"{proc.stdout}\n{proc.stderr}"
    )
    assert "verify-substrate: PASS" in proc.stdout, proc.stdout


def test_ci_runs_enforce_verify_substrate():
    """CI must guard substrate coherence with `atdd enforce --verify-substrate`."""
    steps = _enforce_run_steps()
    assert any("--verify-substrate" in run for _, _, run in steps), (
        "no CI step runs `atdd enforce --verify-substrate` in atdd-validate.yml"
    )


def test_ci_enforce_verdict_is_blocking():
    """GT-900 mechanism: the `atdd enforce` VERDICT step is BLOCKING (#1428 E001).

    A verdict step is any `atdd enforce` invocation that is NOT `--verify-substrate`.
    It must carry NEITHER swallow guard — no ``continue-on-error: true``, no
    ``|| true`` — so a strict convention FAIL exits the job non-zero and blocks the
    merge via the validate-gate fan-in.

    This INVERTS the #1359 assertion. #1359 shipped the verdict as a deliberate
    ADVISORY ratchet STAGE because the toolkit did not pass its own rules; #1428 ends
    that stage by pairing the flip with `.atdd/enforce-ratchet.yaml`, a per-rule
    violation-count baseline that holds the pre-existing debt flat while failing any
    regression. The stage was never the destination.
    """
    verdict_steps = [
        (job, step, run)
        for job, step, run in _enforce_run_steps()
        if "--verify-substrate" not in run
    ]
    assert verdict_steps, "CI must run the `atdd enforce` verdict (a non --verify-substrate invocation)"
    for job, step, run in verdict_steps:
        assert step.get("continue-on-error") is not True, (
            f"the `atdd enforce` verdict step in job {job!r} carries "
            f"`continue-on-error: true` — a strict FAIL would report SUCCESS (#1428)"
        )
        assert "|| true" not in run, (
            f"the `atdd enforce` verdict step in job {job!r} pipes through `|| true` "
            f"— a strict FAIL would report SUCCESS (#1428)"
        )
        # Blocking WITHOUT the ratchet would red the build on pre-existing debt: the
        # flip and the baseline are one change, never two.
        assert "--ratchet" in run, (
            f"the blocking `atdd enforce` verdict step in job {job!r} must judge "
            f"against the recorded ratchet baseline (#1428 E003)"
        )
