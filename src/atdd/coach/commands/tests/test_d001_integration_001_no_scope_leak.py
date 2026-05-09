# URN: test:drive-state-machine:coach-state-machine-and-runtime:D001-INTEGRATION-001-no-scope-leak
# Acceptance: acc:drive-state-machine:D001-INTEGRATION-001-no-scope-leak
# WMBT: wmbt:drive-state-machine:D001
# Phase: RED
# Layer: integration
"""D001-INTEGRATION-001 — J1 must not bleed into adjacent tracks.

Each `Out of Scope` bullet in #496 names the issue that owns that
concern. This test verifies coach.py imports (and source) contain no
references to those forbidden subsystems.
"""
from __future__ import annotations

import inspect

import pytest

pytestmark = [pytest.mark.platform]


COACH_MODULE = "atdd.coach.commands.coach"

# Each (substring, owning_issue) — substring lookups are intentionally
# string-based so this test catches both module imports and dotted-path
# references in comments.
SCOPE_LEAK_FORBIDDEN: list[tuple[str, str]] = [
    # Watcher attachment — #J5
    ("inotify", "#J5 (watcher attachment)"),
    ("fswatch", "#J5 (watcher attachment)"),
    # Validator dispatch — #M3
    ("violation_collector", "#M3 (validator dispatch)"),
    ("suppression_scanner", "#M3 (validator dispatch)"),
    # Observer integration — #L1
    ("observer_correction", "#L1 (observer integration)"),
    # Spawn integration — #K1
    ("session_template", "#K1 (spawn integration)"),
    ("apply_canonical_name_and_layout", "#K1 (spawn integration)"),
    # Two-phase commit — #J4 / E001
    ("_create_worktree", "#J4 (two-phase commit)"),
    ("_remove_worktree", "#J4 (two-phase commit)"),
    # Decision durability — #J3
    ("decisions.jsonl", "#J3 (decision durability)"),
    ("judgments.jsonl", "#J3 (decision durability)"),
    # Resume — #J6
    ("resume_from_decisions", "#J6 (resume reconstruction)"),
]


def test_coach_module_imports_only_skeleton_dependencies():
    """coach.py source must not reference adjacent-track machinery."""
    coach_mod = __import__(COACH_MODULE, fromlist=["*"])
    src = inspect.getsource(coach_mod)

    leaks = [
        (substring, owner)
        for substring, owner in SCOPE_LEAK_FORBIDDEN
        if substring in src
    ]
    assert not leaks, (
        "coach.py contains scope-leak references to adjacent tracks:\n"
        + "\n".join(f"  - {sub!r} → {owner}" for sub, owner in leaks)
    )


def test_coach_does_not_import_pytest_subprocess():
    """No validator dispatch — coach.py must not import pytest-as-runner."""
    coach_mod = __import__(COACH_MODULE, fromlist=["*"])
    imported = set(getattr(coach_mod, "__dict__", {}).keys())

    assert "pytest" not in imported


def test_coach_does_not_import_multiplexer_or_session_template():
    """Spawn integration lives in #K1, not J1."""
    coach_mod = __import__(COACH_MODULE, fromlist=["*"])
    src = inspect.getsource(coach_mod)

    assert "from atdd.coach.commands.session_template" not in src
    assert "from atdd.coach.utils.multiplexer" not in src


def test_coach_module_does_not_open_jsonl_writers():
    """Decision durability lives in #J3, not J1."""
    coach_mod = __import__(COACH_MODULE, fromlist=["*"])
    src = inspect.getsource(coach_mod)

    # The whole point of J1 is no .jsonl writes happen.
    assert ".jsonl" not in src


def test_resume_flag_parses_but_does_not_reconstruct(monkeypatch):
    """`--resume <run-id>` parses but is not yet wired to reconstruction
    logic. R001 (#J6) owns the resume runner."""
    from atdd.coach.commands.coach import parse_cli, run

    cfg = parse_cli(["358", "--resume", "run-abc"])
    assert cfg.resume == "run-abc"

    # Verify run() does NOT walk a decisions.jsonl when --resume is set.
    # (J1 simply ignores the value beyond carrying it in the resolved config.)
    rc = run(issue_numbers=[358], resume="run-abc", dry_run=True)
    assert rc == 0
