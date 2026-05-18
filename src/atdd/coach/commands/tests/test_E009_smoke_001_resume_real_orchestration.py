# URN: test:integration-hardening:coach-resume-wiring:E009-SMOKE-001-resume-real-orchestration
# Acceptance: acc:integration-hardening:E009-SMOKE-001-resume-real-orchestration
# WMBT: wmbt:integration-hardening:E009
# Phase: SMOKE
# Layer: assembly
# Smoke: true
# Execution-Kind: hermetic_integration
# Purpose: exercise `atdd coach --resume` against the REAL transition_action
#          builder, the real spawn handler, the committed persona prompts, and
#          a real decisions.jsonl round-trip on the filesystem.
"""E009 SMOKE — verify the #734 resume-wiring fix against real infrastructure.

Execution kind: ``hermetic_integration`` (issue #690 vocabulary). The subject —
the resume-path orchestration wiring (#734) — is exercised entirely real:

- the REAL ``_make_resume_transition_action`` that ``coach.py`` builds in
  production (no ``_transition_action_override`` seam), so a regression that
  unwires the resume path (the exact #734 bug) is caught end-to-end;
- the REAL spawn handler, which loads the committed
  ``coder/refactor.prompt.yaml`` off disk — a missing or unparseable persona
  prompt would fail here;
- the REAL ``DecisionWriter`` and a real ``decisions.jsonl`` round-trip: the
  original run logs INIT→…→SMOKE, the writer is dropped to mimic process
  death, and a fresh ``coach.run(--resume)`` reconstructs from the on-disk log.

Hermetic fidelity declaration (paired with
``acc:integration-hardening:E009-SMOKE-001`` ``hermetic:`` block):

  permitted fake — ``fake_multiplexer``
    ``utils.multiplexer.FakeMultiplexer`` (and a failing variant), injected
    BY CONSTRUCTION through the ``coach.run(_multiplexer_backend=...)`` seam —
    not via ``monkeypatch``. It records ``new_workspace`` / ``new_surface``
    calls so the phase→persona spawn sequence is assertable.
  known gaps — it does not prove a real cmux daemon accepts the surface RPC,
    nor that the persona command runs in a real terminal pane. ``cmux_rpc``
    fidelity is covered by the multiplexer wagon's own backend tests.

The worktree and runtime dir are real ``tmp_path`` directories, supplied
through the ``_worktree_override`` / ``_runtime_dir_override`` construction
seams — again, no ``monkeypatch.setattr`` of production module globals.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from atdd.coach.utils.multiplexer import FakeMultiplexer

pytestmark = [pytest.mark.platform]


class _FailingMultiplexer(FakeMultiplexer):
    """A FakeMultiplexer whose surface-create RPCs reject — a hermetic stand-in
    for a cmux backend that genuinely cannot spawn the persona.

    Injected by construction (same ``_multiplexer_backend`` seam as the healthy
    fake) so the REAL spawn handler walks its real retry → escalate → ERROR
    path, driving the resume runner to BLOCK instead of paper-stamping COMPLETE.
    The message is deliberately non-transient so no free retry budget applies.
    """

    def new_workspace(self, *args, **kwargs):  # type: ignore[override]
        raise RuntimeError("fake cmux backend: surface-create RPC rejected")

    def new_surface(self, *args, **kwargs):  # type: ignore[override]
        raise RuntimeError("fake cmux backend: surface-create RPC rejected")


def _seed(writer, *, run_id: str, issue: int, src: str, dst: str, ts: str) -> None:
    writer.append({
        "decision_id": f"{run_id}:#{issue}:{src}->{dst}",
        "timestamp": ts,
        "coach_run_id": run_id,
        "issue_number": issue,
        "decision_type": "phase-transition",
        "inputs": {"current_phase": src, "target_phase": dst},
        "outcome": {"transitioned": True, "new_phase": dst},
    })


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _phase_targets(records: list[dict]) -> list[str]:
    return [
        (r.get("inputs") or {}).get("target_phase")
        for r in records
        if r.get("decision_type") == "phase-transition"
    ]


def test_smoke_resume_drives_real_orchestration_on_real_fs(tmp_path):
    """Kill-and-resume on the real filesystem: a SMOKE issue resumed via the
    real ``coach.py`` path spawns the coder persona through the REAL spawn
    handler and reaches COMPLETE — no paper fast-forward."""
    from atdd.coach.commands.coach import run
    from atdd.coach.commands.durability import DecisionWriter

    run_id = "coach-run-734-smoke-001"
    runtime_dir = tmp_path / ".atdd" / "runtime"
    decisions_path = runtime_dir / "coach" / "decisions.jsonl"

    # ----- "Original" run: INIT→PLANNED→RED→GREEN→SMOKE, then process killed.
    writer = DecisionWriter(runtime_dir=runtime_dir)
    _seed(writer, run_id=run_id, issue=999, src="INIT", dst="PLANNED",
          ts="2026-05-17T10:00:00Z")
    _seed(writer, run_id=run_id, issue=999, src="PLANNED", dst="RED",
          ts="2026-05-17T10:01:00Z")
    _seed(writer, run_id=run_id, issue=999, src="RED", dst="GREEN",
          ts="2026-05-17T10:02:00Z")
    _seed(writer, run_id=run_id, issue=999, src="GREEN", dst="SMOKE",
          ts="2026-05-17T10:03:00Z")
    del writer  # mimic process death — no in-memory continuity into resume.

    before = _read_jsonl(decisions_path)
    assert _phase_targets(before) == ["PLANNED", "RED", "GREEN", "SMOKE"]

    # ----- Resumed run: real action builder, real spawn handler, real prompts.
    # The cmux backend and the GitHub-backed worktree resolver are supplied by
    # construction through coach.run's seams — no monkeypatching. The persona
    # prompt loader is NOT redirected: the committed coder/refactor.prompt.yaml
    # is loaded off disk.
    fake_mx = FakeMultiplexer()
    worktree = tmp_path / "wt"
    worktree.mkdir()

    rc = run(
        issue_numbers=[999],
        dry_run=False,
        resume=run_id,
        _runtime_dir_override=runtime_dir,
        _multiplexer_backend=fake_mx,
        _worktree_override=worktree,
        # NOTE: no _transition_action_override — the real
        # _make_resume_transition_action is exercised.
    )

    assert rc == 0, f"resume run must succeed against real infra; rc={rc}"

    # The real spawn handler dispatched a coder persona for SMOKE→REFACTOR.
    spawn_calls = [c for c in fake_mx.calls
                   if c.get("op") in ("new_workspace", "new_surface", "new_surface_in_pane")]
    assert len(spawn_calls) >= 1, (
        f"resuming a SMOKE issue must spawn the pending-phase persona via the "
        f"real action builder; FakeMultiplexer recorded no spawn — the resume "
        f"path paper-walked. calls={fake_mx.calls}"
    )
    coder_calls = [c for c in spawn_calls if "coder" in str(c.get("command") or "")]
    assert len(coder_calls) >= 1, (
        f"SMOKE→REFACTOR must spawn the coder persona; spawn calls={spawn_calls}"
    )

    # The real decisions.jsonl gained the pending transitions only after the
    # orchestration ran.
    after = _read_jsonl(decisions_path)
    targets = _phase_targets(after)
    assert "REFACTOR" in targets, (
        f"the SMOKE→REFACTOR transition was not recorded after real "
        f"orchestration; target_phases={targets}"
    )
    assert "COMPLETE" in targets, (
        f"the resume did not drive the issue to COMPLETE; target_phases={targets}"
    )

    # Idempotency on the real fs: no duplicate decision_ids after resume.
    ids = [r["decision_id"] for r in after]
    assert len(ids) == len(set(ids)), (
        f"duplicate decision_ids on the real fs after resume: {ids}"
    )
    # The already-logged INIT→…→SMOKE transitions were not re-appended.
    assert len(after) > len(before), "resume must append the pending transitions"


def test_smoke_already_complete_resume_is_idempotent_on_real_fs(tmp_path):
    """Resuming a run whose issue reconstructs to COMPLETE does zero
    orchestration and appends zero records — verified through the real
    ``coach.py`` resume path and the real action builder."""
    from atdd.coach.commands.coach import run
    from atdd.coach.commands.durability import DecisionWriter

    run_id = "coach-run-734-smoke-003"
    runtime_dir = tmp_path / ".atdd" / "runtime"
    decisions_path = runtime_dir / "coach" / "decisions.jsonl"

    writer = DecisionWriter(runtime_dir=runtime_dir)
    for src, dst, ts in [
        ("INIT", "PLANNED", "2026-05-17T10:00:00Z"),
        ("PLANNED", "RED", "2026-05-17T10:01:00Z"),
        ("RED", "GREEN", "2026-05-17T10:02:00Z"),
        ("GREEN", "SMOKE", "2026-05-17T10:03:00Z"),
        ("SMOKE", "REFACTOR", "2026-05-17T10:04:00Z"),
        ("REFACTOR", "COMPLETE", "2026-05-17T10:05:00Z"),
    ]:
        _seed(writer, run_id=run_id, issue=999, src=src, dst=dst, ts=ts)
    del writer

    before = _read_jsonl(decisions_path)

    fake_mx = FakeMultiplexer()
    rc = run(
        issue_numbers=[999],
        dry_run=False,
        resume=run_id,
        _runtime_dir_override=runtime_dir,
        _multiplexer_backend=fake_mx,
    )

    assert rc == 0, f"resuming an already-COMPLETE issue must succeed; rc={rc}"
    assert fake_mx.calls == [], (
        f"an already-COMPLETE resume must do zero orchestration; the real spawn "
        f"path was still invoked: {fake_mx.calls}"
    )
    after = _read_jsonl(decisions_path)
    assert len(after) == len(before), (
        f"no new record may be appended on an idempotent resume; "
        f"{len(before)} -> {len(after)} records"
    )


def test_smoke_blocked_resume_escalates_without_fast_forward_on_real_fs(
    tmp_path, capsys
):
    """A resume whose pending phase genuinely cannot complete — the injected
    cmux backend rejects every surface-create RPC, so the real spawn handler
    exhausts its retries and returns ERROR — BLOCKs: it writes a real
    escalation entry, returns non-zero, and stamps neither REFACTOR nor
    COMPLETE into the real decisions.jsonl."""
    from atdd.coach.commands.coach import run
    from atdd.coach.commands.durability import DecisionWriter

    run_id = "coach-run-734-smoke-002"
    runtime_dir = tmp_path / ".atdd" / "runtime"
    decisions_path = runtime_dir / "coach" / "decisions.jsonl"

    writer = DecisionWriter(runtime_dir=runtime_dir)
    _seed(writer, run_id=run_id, issue=999, src="INIT", dst="PLANNED",
          ts="2026-05-17T10:00:00Z")
    _seed(writer, run_id=run_id, issue=999, src="PLANNED", dst="RED",
          ts="2026-05-17T10:01:00Z")
    _seed(writer, run_id=run_id, issue=999, src="RED", dst="GREEN",
          ts="2026-05-17T10:02:00Z")
    _seed(writer, run_id=run_id, issue=999, src="GREEN", dst="SMOKE",
          ts="2026-05-17T10:03:00Z")
    del writer

    # Genuine fault injection at the real boundary: the cmux backend rejects
    # the surface-create RPC. The real spawn handler then exhausts its retry
    # budget → returns HandlerResult.ERROR → the real _make_resume_transition_action
    # raises → coach.py must BLOCK + escalate.
    failing_mx = _FailingMultiplexer()
    worktree = tmp_path / "wt"
    worktree.mkdir()
    esc_path = tmp_path / "escalations.log"

    rc = run(
        issue_numbers=[999],
        dry_run=False,
        resume=run_id,
        escalation_channel=f"file:{esc_path}",
        _runtime_dir_override=runtime_dir,
        _multiplexer_backend=failing_mx,
        _worktree_override=worktree,
    )

    records = _read_jsonl(decisions_path)
    targets = _phase_targets(records)
    assert "REFACTOR" not in targets, (
        f"a blocked SMOKE→REFACTOR transition was paper-stamped anyway; "
        f"target_phases={targets}"
    )
    assert "COMPLETE" not in targets, (
        f"a REFACTOR→COMPLETE record was written past the block — the resume "
        f"paper-walked; target_phases={targets}"
    )

    escalated = esc_path.exists() and esc_path.read_text().strip() != ""
    assert rc != 0 or escalated, (
        f"a blocked resume must surface a BLOCK/escalation outcome — non-zero "
        f"rc or an escalation entry on the real fs; rc={rc}, "
        f"escalation_written={escalated}"
    )

    out = capsys.readouterr().out
    assert "#999 → COMPLETE" not in out, (
        f"issue 999 must not be reported COMPLETE after a real block; output:\n{out}"
    )
