"""Advisory extension-enforcement gate (#1359).

Guards the MECHANISM #1359 activates against the vendored, committed substrate:

  * the canonical ``.atdd/binding.lock.yaml`` binds a real (non-no-op) coder/tester
    set, and train-interlocking is DEFERRED (#1361, blocked on #1292/#1345) — an
    unresolvable bind would break ``--verify-substrate`` and the gate;
  * ``atdd enforce --verify-substrate`` passes against the committed vendored tree
    (digest coherence — a real, blocking invariant);
  * CI wires ``atdd enforce`` and runs its VERDICT as an ADVISORY (non-blocking)
    ratchet stage — the toolkit does not yet pass its own extension rules, so a FAIL
    verdict must not break the build. The flip to a BLOCKING gate is a tracked
    follow-up (decommission #1207 + extract orchestration out of core).

These are fast + dependency-light (no tree-sitter): the heavy convention verdict is
produced by the advisory CI step itself, visible in the CI log, not re-run here.
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


def test_binding_lock_binds_runnable_set_without_train_interlocking():
    """GT-001: the canonical lock binds a non-empty coder/tester set; train-interlocking omitted (#1361)."""
    assert BINDING_LOCK.is_file(), f"canonical binding.lock missing at {BINDING_LOCK}"
    lock = yaml.safe_load(BINDING_LOCK.read_text(encoding="utf-8")) or {}
    bound = [c for c in lock.get("conventions", []) if c.get("disposition") == "bound"]
    assert bound, "binding.lock has no bound conventions — enforce would be a silent no-op"
    ids = {c["convention_id"] for c in bound}
    assert any(i.startswith(("coder.", "tester.")) for i in ids), (
        f"expected coder/tester bound conventions, got: {sorted(ids)}"
    )
    # train-interlocking is deferred to #1361 (blocked on #1292/#1345): the core
    # composer cannot yet compose its list-valued realizes_convention, and an
    # unresolvable bound entry would fail --verify-substrate and break the gate.
    assert not any("interlocking" in i for i in ids), (
        "train-interlocking must NOT be bound here — deferred to #1361 (#1292/#1345)"
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


def test_ci_enforce_verdict_is_advisory():
    """GT-900 mechanism: the `atdd enforce` VERDICT step is advisory (non-blocking ratchet stage).

    A verdict step is any `atdd enforce` invocation that is NOT `--verify-substrate`.
    It must be non-blocking (``continue-on-error: true`` or ``|| true``) so the
    toolkit's current self-debt (13/25 rules) does not break the build — this is an
    explicit ratchet stage, not the destination (#1359).
    """
    verdict_steps = [
        (job, step, run)
        for job, step, run in _enforce_run_steps()
        if "--verify-substrate" not in run
    ]
    assert verdict_steps, "CI must run the `atdd enforce` verdict (a non --verify-substrate invocation)"
    for job, step, run in verdict_steps:
        advisory = step.get("continue-on-error") is True or "|| true" in run
        assert advisory, (
            f"the `atdd enforce` verdict step in job {job!r} must be ADVISORY "
            f"(continue-on-error: true or `|| true`) — #1359 ratchet stage"
        )
