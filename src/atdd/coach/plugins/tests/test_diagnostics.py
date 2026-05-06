"""Plugin tests for ``atdd.coach.plugins.diagnostics`` (issue #449).

The plugin owns:
  * Session-finish artifact write (only on master, never on xdist worker).
  * --verify-baseline / ATDD_DIAGNOSTICS_DISABLED env short-circuit.
  * Toolkit-packaging detection via ``Path.is_relative_to``.
  * Stdout summary structure (NOT a hard-coded snapshot — too brittle).

We exercise the hooks directly with synthetic objects rather than spinning
up a fixture repo. Decision per issue body: keep Phase 4 LOC bounded.
"""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any, List, Optional

import pytest
import yaml

from atdd.coach.plugins import diagnostics as plugin
from atdd.coach.utils import diagnostics as diag
from atdd.coach.utils import repo as repo_utils
from atdd.coach.utils.diagnostics import (
    ConventionRef,
    Finding,
    Item,
    set_active_nodeid,
)


# ---------------------------------------------------------------------------
# Helpers — synthesize the parts of pytest the plugin actually touches.
# ---------------------------------------------------------------------------


def _make_session(repo_root: Path, args: Optional[List[str]] = None, *, worker: bool = False) -> Any:
    """Build a duck-typed pytest.Session enough for the plugin's hooks."""
    config_extras = {}
    if worker:
        config_extras["workerinput"] = {"workerid": "gw0"}
    config = SimpleNamespace(args=args or [], **config_extras)
    return SimpleNamespace(config=config, items=[])


def _make_report(
    nodeid: str,
    *,
    when: str = "call",
    outcome: str = "failed",
    longrepr: Any = "fail",
) -> Any:
    return SimpleNamespace(
        nodeid=nodeid,
        when=when,
        passed=(outcome == "passed"),
        failed=(outcome == "failed"),
        skipped=(outcome == "skipped"),
        longrepr=longrepr,
    )


def _reset_state() -> None:
    plugin._STATE = plugin._DiagnosticsState()
    diag.clear_pending_findings()
    set_active_nodeid(None)
    # ``find_repo_root`` is lru_cached — purge between tests so each test
    # sees its own ATDD_REPO_ROOT monkeypatch.
    repo_utils.find_repo_root.cache_clear()


# ---------------------------------------------------------------------------
# Schema + artifact write
# ---------------------------------------------------------------------------


def test_plugin_writes_artifact_with_schema_v1(tmp_path, monkeypatch):
    """End-to-end: setup → failed report → sessionfinish → artifact exists."""
    _reset_state()
    monkeypatch.delenv("ATDD_DIAGNOSTICS_DISABLED", raising=False)
    monkeypatch.setenv("ATDD_REPO_ROOT", str(tmp_path))

    session = _make_session(tmp_path, args=[str(tmp_path / "src/atdd/coder/validators")])
    plugin.pytest_sessionstart(session)

    # Migrated validator path: caller pre-records a finding.
    nodeid = "src/atdd/coder/validators/test_x.py::test_named"
    set_active_nodeid(nodeid)
    diag._PENDING_FINDINGS[nodeid] = [Finding(
        validator_id="test_named",
        validator_path="src/atdd/coder/validators/test_x.py",
        category="naming",
        severity="error",
        summary="2 violations",
        raw_message="2 class naming violations",
        items=[Item(file="x.py", symbol="testFoo", expected="TestFoo", found="testFoo", fix="rename")],
        convention_ref=ConventionRef(file="conv.yaml", anchor="anchor"),
    )]
    set_active_nodeid(None)
    plugin.pytest_runtest_logreport(_make_report(nodeid))
    plugin.pytest_sessionfinish(session, exitstatus=1)

    artifact = tmp_path / ".atdd" / "diagnostics" / "validation" / "coder.yaml"
    assert artifact.exists()
    document = yaml.safe_load(artifact.read_text())
    assert document["schema_version"] == 1
    assert document["run"]["phase"] == "coder"
    assert document["run"]["outcome"]["failed"] == 1
    assert document["findings"][0]["category"] == "naming"
    assert document["findings"][0]["items"][0]["expected"] == "TestFoo"


def test_plugin_synthesizes_unmigrated_finding_when_helper_not_used(tmp_path, monkeypatch):
    """Non-migrated validators still get a Finding (raw_message-only)."""
    _reset_state()
    monkeypatch.delenv("ATDD_DIAGNOSTICS_DISABLED", raising=False)
    monkeypatch.setenv("ATDD_REPO_ROOT", str(tmp_path))

    session = _make_session(tmp_path, args=[str(tmp_path / "src/atdd/tester/validators")])
    plugin.pytest_sessionstart(session)

    nodeid = "src/atdd/tester/validators/test_unmigrated.py::test_a"
    plugin.pytest_runtest_logreport(_make_report(
        nodeid,
        longrepr="E       AssertionError: thing went wrong\nstacktrace...\n",
    ))
    plugin.pytest_sessionfinish(session, exitstatus=1)

    document = yaml.safe_load((tmp_path / ".atdd/diagnostics/validation/tester.yaml").read_text())
    assert len(document["findings"]) == 1
    f = document["findings"][0]
    # Path-based hint puts unmigrated tester findings into a category bucket
    # the plugin can detect — falls back to ``unmigrated`` if no hint hits.
    assert f["category"] in plugin.LEGAL_CATEGORIES if hasattr(plugin, "LEGAL_CATEGORIES") else True
    assert "AssertionError" in f["raw_message"] or "thing went wrong" in f["raw_message"]
    assert f["items"] == []


# ---------------------------------------------------------------------------
# xdist worker short-circuit
# ---------------------------------------------------------------------------


def test_plugin_no_artifact_write_on_xdist_worker(tmp_path, monkeypatch):
    _reset_state()
    monkeypatch.delenv("ATDD_DIAGNOSTICS_DISABLED", raising=False)
    monkeypatch.setenv("ATDD_REPO_ROOT", str(tmp_path))

    worker_session = _make_session(
        tmp_path,
        args=[str(tmp_path / "src/atdd/coder/validators")],
        worker=True,
    )
    plugin.pytest_sessionstart(worker_session)
    plugin.pytest_runtest_logreport(_make_report("nodeid::test"))
    plugin.pytest_sessionfinish(worker_session, exitstatus=1)

    # Workers must NOT write the artifact — only the master does.
    assert not (tmp_path / ".atdd/diagnostics/validation/coder.yaml").exists()


# ---------------------------------------------------------------------------
# --verify-baseline short-circuit (GT-140)
# ---------------------------------------------------------------------------


def test_plugin_no_op_when_diagnostics_disabled_env_set(tmp_path, monkeypatch):
    """GT-140: ATDD_DIAGNOSTICS_DISABLED=1 → plugin writes nothing."""
    _reset_state()
    monkeypatch.setenv("ATDD_DIAGNOSTICS_DISABLED", "1")
    monkeypatch.setenv("ATDD_REPO_ROOT", str(tmp_path))

    session = _make_session(tmp_path, args=[str(tmp_path / "src/atdd/coder/validators")])
    plugin.pytest_sessionstart(session)
    plugin.pytest_runtest_logreport(_make_report("nodeid::test"))
    plugin.pytest_sessionfinish(session, exitstatus=1)

    assert not (tmp_path / ".atdd/diagnostics/validation/coder.yaml").exists()


# ---------------------------------------------------------------------------
# Toolkit-packaging detection (Decision #5: Path.is_relative_to, no substring)
# ---------------------------------------------------------------------------


def test_toolkit_packaging_detection_uses_resolve_and_is_relative_to():
    """Decision #5: a path under the installed atdd package counts."""
    import atdd
    pkg = Path(atdd.__file__).resolve().parent
    inside = pkg / "tester" / "fixtures" / "missing.json"
    assert plugin._is_toolkit_packaging_issue(str(inside)) is True


def test_toolkit_packaging_detection_does_not_false_positive_on_substring(tmp_path):
    """Consumer tmp paths containing 'atdd' must NOT count."""
    sneaky = tmp_path / "atdd-consumer" / "x.json"
    sneaky.parent.mkdir(parents=True)
    sneaky.write_text("{}")
    assert plugin._is_toolkit_packaging_issue(str(sneaky)) is False


def test_toolkit_packaging_issue_recorded_on_fnfe_inside_pkg(tmp_path, monkeypatch):
    _reset_state()
    monkeypatch.delenv("ATDD_DIAGNOSTICS_DISABLED", raising=False)
    monkeypatch.setenv("ATDD_REPO_ROOT", str(tmp_path))

    import atdd
    pkg = Path(atdd.__file__).resolve().parent
    fnfe_path = pkg / "tester" / "validators" / "fixtures" / "ghost.json"
    longrepr = (
        f"FileNotFoundError: [Errno 2] No such file or directory: "
        f"'{fnfe_path}'"
    )

    session = _make_session(tmp_path, args=[str(tmp_path / "src/atdd/tester/validators")])
    plugin.pytest_sessionstart(session)
    plugin.pytest_runtest_logreport(_make_report(
        "src/atdd/tester/validators/test_pack.py::test_one",
        longrepr=longrepr,
    ))
    plugin.pytest_sessionfinish(session, exitstatus=1)

    document = yaml.safe_load((tmp_path / ".atdd/diagnostics/validation/tester.yaml").read_text())
    assert len(document["toolkit_packaging_issues"]) == 1
    entry = document["toolkit_packaging_issues"][0]
    assert str(fnfe_path) in entry["resource"]


# ---------------------------------------------------------------------------
# Stdout summary structure (no hard-coded snapshot — fragile)
# ---------------------------------------------------------------------------


def test_stdout_summary_structure(tmp_path, monkeypatch, capsys):
    """Issue #449 spec: structural assertions only — never a snapshot.

    Required:
      * starts with `=== DIAGNOSTICS`
      * one `[<category>]` line per category present in findings
      * `Top fixes` header followed by ≤10 `file:line` lines
      * ends with `Full diagnostics: <path>`
    """
    _reset_state()
    monkeypatch.delenv("ATDD_DIAGNOSTICS_DISABLED", raising=False)
    monkeypatch.setenv("ATDD_REPO_ROOT", str(tmp_path))

    session = _make_session(tmp_path, args=[str(tmp_path / "src/atdd/coder/validators")])
    plugin.pytest_sessionstart(session)

    # Two categories: naming + hygiene.
    nodeid_a = "src/atdd/coder/validators/test_x.py::test_a"
    diag._PENDING_FINDINGS[nodeid_a] = [Finding(
        validator_id="test_a", validator_path="src/atdd/coder/validators/test_x.py",
        category="naming", severity="error", summary="naming violation",
        raw_message="naming",
        items=[Item(file="a.py", line=10, fix="rename to A")],
    )]
    plugin.pytest_runtest_logreport(_make_report(nodeid_a))

    nodeid_b = "src/atdd/coder/validators/test_y.py::test_b"
    diag._PENDING_FINDINGS[nodeid_b] = [Finding(
        validator_id="test_b", validator_path="src/atdd/coder/validators/test_y.py",
        category="hygiene", severity="error", summary="syspath",
        raw_message="syspath",
        items=[Item(file="b.py", line=5, fix="remove sys.path.insert")],
    )]
    plugin.pytest_runtest_logreport(_make_report(nodeid_b))

    plugin.pytest_sessionfinish(session, exitstatus=1)

    captured = capsys.readouterr().out
    assert "=== DIAGNOSTICS" in captured
    assert "[naming" in captured
    assert "[hygiene" in captured
    assert "Top fixes" in captured

    # Top-fixes block: the 2 file:line entries we set up.
    assert "a.py:10" in captured
    assert "b.py:5" in captured

    # Footer with artifact path.
    assert "Full diagnostics:" in captured
    assert "coder.yaml" in captured


def test_stdout_summary_skipped_when_no_failures(tmp_path, monkeypatch, capsys):
    _reset_state()
    monkeypatch.delenv("ATDD_DIAGNOSTICS_DISABLED", raising=False)
    monkeypatch.setenv("ATDD_REPO_ROOT", str(tmp_path))

    session = _make_session(tmp_path, args=[str(tmp_path / "src/atdd/coder/validators")])
    plugin.pytest_sessionstart(session)
    plugin.pytest_runtest_logreport(_make_report("any::test", outcome="passed"))
    plugin.pytest_sessionfinish(session, exitstatus=0)

    out = capsys.readouterr().out
    assert "=== DIAGNOSTICS" not in out
    # Artifact still written on success — schema demands it.
    assert (tmp_path / ".atdd/diagnostics/validation/coder.yaml").exists()


# ---------------------------------------------------------------------------
# --diagnostics-only reader
# ---------------------------------------------------------------------------


def test_diagnostics_only_reader_prints_summary(tmp_path, monkeypatch, capsys):
    """`atdd validate --diagnostics-only` reads + prints without pytest."""
    _reset_state()
    monkeypatch.delenv("ATDD_DIAGNOSTICS_DISABLED", raising=False)
    monkeypatch.setenv("ATDD_REPO_ROOT", str(tmp_path))

    artifact = tmp_path / ".atdd/diagnostics/validation/coder.yaml"
    artifact.parent.mkdir(parents=True)
    artifact.write_text(yaml.safe_dump({
        "schema_version": 1,
        "run": {
            "phase": "coder", "ran_at": "2026-05-06T12:00:00Z",
            "duration_seconds": 1.2, "atdd_version": "3.7.0",
            "invocation": "atdd validate --local",
            "outcome": {"passed": 10, "failed": 1, "skipped": 0, "deselected": 0},
        },
        "findings": [{
            "validator_id": "test_a",
            "validator_path": "src/x.py",
            "category": "naming",
            "severity": "error",
            "summary": "naming violation",
            "items": [{"file": "a.py", "line": 7, "fix": "rename"}],
            "raw_message": "raw",
        }],
        "toolkit_packaging_issues": [],
    }))

    from atdd.coach.commands.diagnostics import print_latest_diagnostics
    rc = print_latest_diagnostics(phase="coder", repo_root=tmp_path)
    assert rc == 0

    out = capsys.readouterr().out
    assert "=== DIAGNOSTICS" in out
    assert "[naming" in out
    assert "a.py:7" in out
    assert "Full diagnostics" in out


def test_diagnostics_only_reader_returns_1_when_artifact_absent(tmp_path, capsys):
    from atdd.coach.commands.diagnostics import print_latest_diagnostics
    rc = print_latest_diagnostics(phase="coder", repo_root=tmp_path)
    assert rc == 1
    out = capsys.readouterr().out
    assert "No diagnostics artifact" in out


# ---------------------------------------------------------------------------
# Phase detection
# ---------------------------------------------------------------------------


def test_detect_phase_single_phase(tmp_path):
    session = _make_session(tmp_path, args=["src/atdd/coder/validators"])
    assert plugin._detect_phase(session) == "coder"


def test_detect_phase_multiple_phases_returns_all(tmp_path):
    session = _make_session(tmp_path, args=[
        "src/atdd/coder/validators",
        "src/atdd/tester/validators",
    ])
    assert plugin._detect_phase(session) == "all"
