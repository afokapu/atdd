# URN: test:govern-lifecycle:extract-workflow-issue-runner-and-workflow-runner-protocol:E041-UNIT-004-issue-runner-move-and-deprecated-shims
# Acceptance: acc:govern-lifecycle:E041-UNIT-004-issue-runner-move-and-deprecated-shims
"""Unit test for E041-UNIT-004 (docs/coach-decomposition.md §11, §5.2, §13.8).

The four orchestration functions live in ``atdd.train.issue_runner``; ``coach.py``
keeps ``@deprecated(removal="3.87.0")`` compatibility shims that delegate; adding
a new event type is a pure ``events.jsonl`` schema bump with no Coach-core change.
"""
from __future__ import annotations

import ast
import warnings
from pathlib import Path

import atdd
from atdd.coach.commands import coach
from atdd.train import issue_runner


def test_orchestration_functions_live_in_train_issue_runner():
    for name in (
        "drive_single_issue",
        "_process_watcher_events",
        "_process_injected_events",
        "make_resume_transition_action",
    ):
        assert hasattr(issue_runner, name), f"issue_runner missing {name!r}"


def test_coach_keeps_deprecated_shims_that_delegate():
    for name in (
        "_drive_single_issue",
        "_process_watcher_events",
        "_process_injected_events",
        "_make_resume_transition_action",
    ):
        assert hasattr(coach, name), f"coach shim missing {name!r}"


def test_calling_a_shim_warns_and_delegates(tmp_path, monkeypatch):
    """The _make_resume_transition_action shim warns + returns the train action."""
    sentinel = object()
    monkeypatch.setattr(
        issue_runner, "make_resume_transition_action", lambda *a, **k: sentinel
    )
    cfg = coach.Config(issue_numbers=[895], resume="coach-resume-895")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = coach._make_resume_transition_action(cfg, tmp_path)
    assert result is sentinel
    assert any(issubclass(w.category, DeprecationWarning) for w in caught)
    assert any("3.87.0" in str(w.message) for w in caught)


def test_new_event_type_is_a_pure_schema_bump_no_coach_core_change():
    """RunCancelled (added in Child 8) validates without touching Coach-core."""
    from atdd.train.events import EVENT_TYPES, SCHEMA_VERSION, validate_event_dict

    assert "RunCancelled" in EVENT_TYPES

    event = {
        "schema_version": SCHEMA_VERSION,
        "ts": "2026-05-31T00:00:00.000Z",
        "run_id": "run-895-x",
        "issue_number": 895,
        "type": "RunCancelled",
        "payload": {"reason": "operator aborted"},
        "seq": 7,
    }
    assert validate_event_dict(event) == ()

    # The event schema lives entirely in the train layer: coach.core imports
    # nothing from atdd.train and needs no edit to support a new event type.
    cc_dir = Path(atdd.__file__).resolve().parent / "coach" / "core"
    for py in cc_dir.rglob("*.py"):
        tree = ast.parse(py.read_text())
        for node in ast.walk(tree):
            mods: list[str] = []
            if isinstance(node, ast.Import):
                mods = [n.name for n in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                mods = [node.module]
            for m in mods:
                assert not m.startswith("atdd.train"), (
                    f"{py.name} imports {m!r} — coach.core must not depend on the train layer"
                )
