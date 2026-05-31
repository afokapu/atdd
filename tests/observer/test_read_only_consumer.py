# URN: test:govern-lifecycle:split-spawn-and-final-purity-sweep:E042-UNIT-002-observer-read-only-consumer
# Acceptance: acc:govern-lifecycle:E042-UNIT-002-atdd-observer-never-writes-events-or-output-log
# WMBT: wmbt:govern-lifecycle:E042
# Phase: RED
# Layer: backend.application
"""``atdd.observer`` is a first-class READ-ONLY consumer (§8, #897).

Acceptance (§13.10): "``atdd observer`` runs without ever writing to
``events.jsonl`` or ``output.log`` (file-watcher only)." These tests prove the
no-write invariant two ways: (1) the artifacts are byte-identical after a full
stream pass, and (2) the module never opens either file in a write mode.
"""
from __future__ import annotations

import ast
import builtins
import json
from pathlib import Path

import pytest

import atdd.observer as observer

REPO_ROOT = Path(__file__).resolve().parents[2]


def _seed_run(repo_root: Path, run_id: str, events: list[dict]) -> Path:
    run_dir = repo_root / ".atdd" / "runtime" / "runs" / run_id
    run_dir.mkdir(parents=True)
    events_file = run_dir / "events.jsonl"
    events_file.write_text("".join(json.dumps(e) + "\n" for e in events), encoding="utf-8")
    return events_file


# --------------------------------------------------------------------------- #
# read behavior
# --------------------------------------------------------------------------- #
def test_aggregates_events_across_runs(tmp_path):
    _seed_run(tmp_path, "run-a", [{"seq": 1, "event_type": "RunStarted"},
                                  {"seq": 2, "event_type": "PhaseAdvanced"}])
    _seed_run(tmp_path, "run-b", [{"seq": 1, "event_type": "RunStarted"}])

    events = observer.aggregate_events(tmp_path)

    assert [e["run_id"] for e in events] == ["run-a", "run-a", "run-b"]
    assert observer.list_run_ids(tmp_path) == ["run-a", "run-b"]


def test_partial_trailing_line_is_skipped_not_repaired(tmp_path):
    events_file = _seed_run(tmp_path, "run-a", [{"seq": 1, "event_type": "RunStarted"}])
    # Simulate a writer mid-append: a partial JSON line at EOF.
    with events_file.open("a", encoding="utf-8") as fh:
        fh.write('{"seq": 2, "event_ty')
    before = events_file.read_bytes()

    parsed = observer.read_events(tmp_path, "run-a")

    assert len(parsed) == 1, "partial line must be skipped"
    assert events_file.read_bytes() == before, "observer must not repair/rewrite the file"


# --------------------------------------------------------------------------- #
# the no-write invariant (acceptance #2)
# --------------------------------------------------------------------------- #
def test_view_never_writes_events_or_output_log(tmp_path, monkeypatch):
    events_file = _seed_run(tmp_path, "run-a", [{"seq": 1, "event_type": "RunStarted"}])
    agent_dir = tmp_path / ".atdd" / "runtime" / "runs" / "run-a"
    output_log = agent_dir / "output.log"
    output_log.write_text("worker line 1\nworker line 2\n", encoding="utf-8")

    events_before = events_file.read_bytes()
    output_before = output_log.read_bytes()

    # Guard: trap any write-mode open of the two single-writer artifacts.
    real_open = builtins.open
    protected = {str(events_file), str(output_log)}

    def _guarded_open(file, mode="r", *args, **kwargs):
        if str(file) in protected and any(m in mode for m in ("w", "a", "x", "+")):
            raise AssertionError(f"observer opened {file} in write mode {mode!r}")
        return real_open(file, mode, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", _guarded_open)

    rc = observer.run(["--repo-root", str(tmp_path), "--output-log", str(output_log)])

    assert rc == 0
    assert events_file.read_bytes() == events_before, "events.jsonl must be untouched"
    assert output_log.read_bytes() == output_before, "output.log must be untouched"


def test_observer_module_has_no_write_mode_opens():
    """Static guard: no ``open(..., 'w'/'a'/...)`` anywhere in atdd.observer."""
    src = Path(observer.__file__)
    tree = ast.parse(src.read_text())
    bad: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            is_open = (isinstance(func, ast.Name) and func.id == "open") or (
                isinstance(func, ast.Attribute) and func.attr == "open"
            )
            if not is_open:
                continue
            # mode may be the 2nd positional arg or a `mode=` kw
            mode_arg = node.args[1] if len(node.args) >= 2 else None
            for kw in node.keywords:
                if kw.arg == "mode":
                    mode_arg = kw.value
            if isinstance(mode_arg, ast.Constant) and isinstance(mode_arg.value, str):
                if any(m in mode_arg.value for m in ("w", "a", "x", "+")):
                    bad.append(mode_arg.value)
    assert not bad, f"atdd.observer must never open in write mode; found {bad}"


def test_observer_imports_no_forbidden_layers():
    """§3.3: atdd.observer imports stdlib only (no writer/orchestration layers)."""
    src = Path(observer.__file__)
    tree = ast.parse(src.read_text())
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(n.name for n in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    forbidden = {"atdd.coach", "atdd.runtime", "atdd.integrations"}
    leaked = {imp for imp in imports for fb in forbidden
              if imp == fb or imp.startswith(fb + ".")}
    # atdd.train.persistence is the only train import the observer MAY make
    # (read-only API, §3.3); none is currently needed.
    train_writes = {imp for imp in imports
                    if imp.startswith("atdd.train") and imp != "atdd.train.persistence"}
    assert not leaked, f"observer leaked forbidden imports: {leaked}"
    assert not train_writes, f"observer may only read atdd.train.persistence: {train_writes}"
