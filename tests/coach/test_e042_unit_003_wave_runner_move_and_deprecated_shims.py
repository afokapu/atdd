# URN: test:govern-lifecycle:extract-workflow-wave-runner-and-atdd-resume-cli:E042-UNIT-003-wave-runner-move-and-deprecated-shims
# Acceptance: acc:govern-lifecycle:E042-UNIT-003-wave-runner-move-and-deprecated-shims
"""Unit test for E042-UNIT-003 (docs/coach-decomposition.md §3.3, §11, §13.9).

``resolve_waves`` / ``drive_wave_concurrently`` / ``execute_cold_start`` live in
``atdd.train.wave_runner``; ``coach.py`` keeps ``@deprecated(removal=3.87.0)``
compatibility shims of the matching names that delegate; and the ``run()``
cold-start path drives the wave through the train-layer function.
"""
from __future__ import annotations

import ast
import warnings
from pathlib import Path

import atdd
from atdd.coach.commands import coach
from atdd.train import wave_runner

_SRC = Path(atdd.__file__).resolve().parent


def test_wave_orchestration_functions_live_in_train_wave_runner():
    for name in ("resolve_waves", "drive_wave_concurrently", "execute_cold_start"):
        assert hasattr(wave_runner, name), f"atdd.train.wave_runner must define {name}"


def test_coach_shims_emit_deprecation_and_delegate(monkeypatch):
    calls: dict[str, bool] = {}

    monkeypatch.setattr(
        wave_runner, "resolve_waves",
        lambda cfg: (calls.__setitem__("resolve", True) or [[1]]),
    )
    monkeypatch.setattr(
        wave_runner, "drive_wave_concurrently",
        lambda wave, fn, **k: (calls.__setitem__("drive", True) or {n: 0 for n in wave}),
    )

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        coach._resolve_waves(coach.Config(issue_numbers=[1]))
        coach._drive_wave_concurrently([1], lambda n: 0)

    assert calls.get("resolve") and calls.get("drive"), "shims must delegate to wave_runner"
    msgs = " ".join(str(w.message) for w in caught if issubclass(w.category, DeprecationWarning))
    assert "3.87.0" in msgs and "wave_runner" in msgs


def test_wave_runner_obeys_section_3_3_no_cli_or_observer_import():
    forbidden = ("atdd.cli", "atdd.observer")
    src = _SRC / "train" / "wave_runner.py"
    tree = ast.parse(src.read_text())
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(n.name for n in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    for fb in forbidden:
        assert not any(
            imp == fb or imp.startswith(fb + ".") for imp in imported
        ), f"wave_runner.py imports forbidden {fb!r}"


def test_run_cold_start_drives_via_wave_runner(tmp_path, monkeypatch):
    """run() cold-start constructs the runner+policy and drives via wave_runner."""
    from atdd.train.runner_iface import PolicyHandle
    from atdd.train.runners.jsonl import JsonlTrainRunner

    captured: dict = {}

    def _capture(cfg, machines, runtime_dir, *, runner=None, policy=None, **kwargs):
        captured["runner"] = runner
        captured["policy"] = policy
        return coach.ColdStartResult(rc=0, blocked=[])

    monkeypatch.setattr(wave_runner, "execute_cold_start", _capture)
    monkeypatch.setattr(coach, "_read_current_github_phase", lambda n: None)

    rc = coach.run([895], _runtime_dir_override=tmp_path)
    assert rc == 0
    assert isinstance(captured["runner"], JsonlTrainRunner)
    assert isinstance(captured["policy"], PolicyHandle)
