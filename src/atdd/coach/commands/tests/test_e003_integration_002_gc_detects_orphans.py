# URN: test:spawn-agents:transactional-spawn-and-orphan-pane-gc:E003-INTEGRATION-002-gc-detects-orphans
# Acceptance: acc:spawn-agents:E003-INTEGRATION-002-gc-detects-orphans
# WMBT: wmbt:spawn-agents:E003
# Phase: RED
# Layer: integration
"""E003-INTEGRATION-002 — `atdd coach gc --dry-run` lists exactly the orphans.

`atdd coach gc` reconciles live cmux surfaces in workspace:1 against the
surface refs recorded in `.atdd/runtime/coach/*/decisions.jsonl`. A pane
is an orphan when it carries the default `~/Github/atdd` cwd AND no
decisions.jsonl entry references its surface.

Fixture: 3 decisions.jsonl-referenced surfaces (surface:201/202/203) plus
2 unreferenced default-cwd panes (surface:204/205). `--dry-run` must list
exactly the 2 unreferenced ones and mutate nothing.

Issue #655 — Layer 2: retroactive garbage collection.

cmux contract: `_PANELS_STDOUT` below is the REAL `cmux list-panels`
output shape (cmux 0.63.2), captured live during the #655 SMOKE run and
realigned from the RED phase's fabricated `cwd:<path>` token guess. Spawn
decisions record the surface ref at `outcome.surface_ref` (internal
coach-decision contract).
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]

_DEFAULT_CWD = "~/Github/atdd"

# Real `cmux list-panels --workspace <ws>` output shape (cmux 0.63.2,
# captured live during the #655 SMOKE run): one line per surface,
# `[*| ] surface:N  <type>  [<flags>]  "<label>"` — the cwd/title is the
# quoted trailing string. 3 decisions.jsonl-referenced surfaces + 2
# unreferenced default-cwd orphans.
_PANELS_STDOUT = "\n".join([
    '* surface:201  terminal  [focused]  "/work/feat-coach-655"',
    '  surface:202  terminal  "ATDD655-tester"',
    '  surface:203  terminal  "ATDD655-coder"',
    f'  surface:204  terminal  "{_DEFAULT_CWD}"',
    f'  surface:205  terminal  "{_DEFAULT_CWD}"',
]) + "\n"


def _spawn_decision(surface_ref: str, agent_id: str) -> dict:
    return {
        "decision_id": f"d-{surface_ref.replace(':', '-')}",
        "timestamp": "2026-05-16T10:00:00Z",
        "coach_run_id": "coach-run-655",
        "issue_number": 655,
        "decision_type": "agent_spawned",
        "inputs": {"agent_id": agent_id, "persona": agent_id.split("-")[0]},
        "outcome": {"status": "SPAWNED", "surface_ref": surface_ref},
    }


def _make_fixture_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / ".atdd").mkdir(parents=True)
    (repo / ".atdd" / "manifest.yaml").write_text("version: '1.0'\n", encoding="utf-8")
    run_dir = repo / ".atdd" / "runtime" / "coach" / "coach-run-655"
    run_dir.mkdir(parents=True)
    decisions = run_dir / "decisions.jsonl"
    decisions.write_text(
        "\n".join(
            json.dumps(rec)
            for rec in (
                _spawn_decision("surface:201", "planner-655-aaaa"),
                _spawn_decision("surface:202", "tester-655-bbbb"),
                _spawn_decision("surface:203", "coder-655-cccc"),
            )
        ) + "\n",
        encoding="utf-8",
    )
    return repo


def _install_fake_cmux(monkeypatch) -> list[list[str]]:
    """Patch subprocess.run so `cmux list-panels` returns the fixture and
    every cmux close-* call is recorded. Returns the recording list."""
    recorded: list[list[str]] = []
    real_run = subprocess.run

    def fake_run(cmd, *args, **kwargs):
        argv = list(cmd) if not isinstance(cmd, str) else cmd.split()
        joined = " ".join(str(x) for x in argv)
        if argv[:1] == ["cmux"]:
            recorded.append(argv)
            if "list-panels" in joined or "list-panes" in joined:
                return subprocess.CompletedProcess(argv, 0, _PANELS_STDOUT, "")
            return subprocess.CompletedProcess(argv, 0, "OK\n", "")
        return real_run(cmd, *args, **kwargs)

    monkeypatch.setattr(subprocess, "run", fake_run)
    return recorded


def test_gc_dry_run_lists_exactly_the_two_orphans(tmp_path, monkeypatch, capsys):
    from atdd.coach.commands import coach

    repo = _make_fixture_repo(tmp_path)
    monkeypatch.chdir(repo)
    monkeypatch.setenv("ATDD_REPO_ROOT", str(repo))
    recorded = _install_fake_cmux(monkeypatch)

    # `gc` is not a recognized subcommand yet — run_cli falls through to the
    # issue-number parser and argparse exits 2. Normalise that to an exit
    # code so the failure surfaces as a clear assertion, not a raw SystemExit.
    try:
        exit_code = coach.run_cli(["gc", "--dry-run"])
    except SystemExit as exc:
        exit_code = exc.code if isinstance(exc.code, int) else 1
    out = capsys.readouterr().out

    assert exit_code == 0, f"`atdd coach gc --dry-run` exited non-zero: {exit_code}"

    # The 2 unreferenced default-cwd panes are reported as orphans.
    assert "surface:204" in out, f"orphan surface:204 not listed. output:\n{out}"
    assert "surface:205" in out, f"orphan surface:205 not listed. output:\n{out}"

    # The 3 decisions.jsonl-referenced surfaces are NOT flagged as orphans.
    for ref in ("surface:201", "surface:202", "surface:203"):
        assert ref not in out, (
            f"{ref} is referenced by decisions.jsonl but was listed as an "
            f"orphan. output:\n{out}"
        )

    # --dry-run mutates nothing: no cmux close-* command was issued.
    close_calls = [
        c for c in recorded
        if len(c) >= 2 and c[0] == "cmux" and c[1].startswith("close")
    ]
    assert not close_calls, f"--dry-run must not close anything, got: {close_calls}"
