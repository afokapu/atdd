"""
Unit and smoke tests for `atdd suppress backfill` (issue #482).

WMBT: wmbt:govern-lifecycle:E013

Acceptance URNs covered:
  acc:govern-lifecycle:E013-UNIT-001-backfill-inserts-python-marker
  acc:govern-lifecycle:E013-UNIT-002-backfill-idempotent-on-already-marked
  acc:govern-lifecycle:E013-UNIT-003-backfill-inserts-typescript-marker
  acc:govern-lifecycle:E013-UNIT-004-cli-suppress-backfill-exits-0
  acc:govern-lifecycle:E013-UNIT-005-unknown-rule-exits-nonzero
  acc:govern-lifecycle:E013-UNIT-006-orphaned-baseline-warning-emitted
  acc:govern-lifecycle:E013-UNIT-007-no-coder-yaml-returns-empty
  acc:govern-lifecycle:E013-SMOKE-001-backfill-on-real-fixture-suppresses-violations

Architecture:
  - Pure-logic unit tests exercise suppress_backfill and
    check_orphaned_baseline_keys directly (no subprocess).
  - SMOKE test uses the real scan_silent_swallows_python scanner on a fixture
    file to verify end-to-end behaviour against real infrastructure.
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Tuple
from unittest.mock import patch

import pytest
import yaml

from atdd.coach.validators._violation import Violation

pytestmark = [pytest.mark.coach]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_RULE_ID = "coder.logging.coach-silent-swallow"


def _make_violation(path: Path, lineno: int) -> Violation:
    return Violation(
        rule_id=_RULE_ID,
        severity=4,
        location=f"{path}:{lineno}",
        detail="silent swallow",
    )


def _make_scanner(violations: List[Violation]):
    """Return a scanner callable → (count, violations)."""
    def scanner(repo_root: Path) -> Tuple[int, List[Violation]]:  # noqa: ARG001
        return len(violations), violations
    return scanner


# ---------------------------------------------------------------------------
# acc:govern-lifecycle:E013-UNIT-001
# suppress_backfill inserts python marker on unmarked violation lines
# ---------------------------------------------------------------------------

def test_backfill_inserts_python_marker(tmp_path: Path):
    """E013-UNIT-001: python silent-swallow lines get an inline suppress marker."""
    from atdd.coach.commands.suppress import suppress_backfill, BackfillResult

    src = tmp_path / "app.py"
    src.write_text(
        "def foo():\n"
        "    try:\n"
        "        pass\n"
        "    except Exception:\n"
        "        pass\n"
        "def bar():\n"
        "    try:\n"
        "        pass\n"
        "    except ValueError:\n"
        "        pass\n",
        encoding="utf-8",
    )

    violations = [_make_violation(src, 4), _make_violation(src, 9)]
    scanner = _make_scanner(violations)

    result: BackfillResult = suppress_backfill(
        rule_id=_RULE_ID,
        until="2099-01-01",
        scanner=scanner,
        repo_root=tmp_path,
    )

    lines = src.read_text(encoding="utf-8").splitlines()
    assert f"# atdd:suppress({_RULE_ID}) UNTIL=2099-01-01" in lines[3]
    assert f"# atdd:suppress({_RULE_ID}) UNTIL=2099-01-01" in lines[8]
    assert result.edited_count == 2
    assert result.skipped_count == 0
    assert src in result.files_touched


# ---------------------------------------------------------------------------
# acc:govern-lifecycle:E013-UNIT-002
# suppress_backfill is idempotent when markers already present
# ---------------------------------------------------------------------------

def test_backfill_idempotent_on_already_marked(tmp_path: Path):
    """E013-UNIT-002: re-running on already-marked file produces edited_count=0."""
    from atdd.coach.commands.suppress import suppress_backfill, BackfillResult

    marker = f"# atdd:suppress({_RULE_ID}) UNTIL=2099-01-01"
    src = tmp_path / "app.py"
    src.write_text(
        f"    except Exception:  {marker}\n"
        f"    except ValueError:  {marker}\n",
        encoding="utf-8",
    )

    violations = [_make_violation(src, 1), _make_violation(src, 2)]
    scanner = _make_scanner(violations)

    result: BackfillResult = suppress_backfill(
        rule_id=_RULE_ID,
        until="2099-01-01",
        scanner=scanner,
        repo_root=tmp_path,
    )

    assert result.edited_count == 0
    assert result.skipped_count == 2
    # File content must not change
    content_after = src.read_text(encoding="utf-8")
    assert content_after.count(marker) == 2


# ---------------------------------------------------------------------------
# acc:govern-lifecycle:E013-UNIT-003
# suppress_backfill inserts TypeScript // marker
# ---------------------------------------------------------------------------

def test_backfill_inserts_typescript_marker(tmp_path: Path):
    """E013-UNIT-003: .ts violation lines get a // inline suppress marker."""
    from atdd.coach.commands.suppress import suppress_backfill, BackfillResult

    ts_file = tmp_path / "handler.ts"
    ts_file.write_text(
        "function foo() {\n"
        "  try { } catch (e) { }  // bare swallow\n"
        "}\n",
        encoding="utf-8",
    )

    violations = [_make_violation(ts_file, 2)]
    scanner = _make_scanner(violations)

    result: BackfillResult = suppress_backfill(
        rule_id=_RULE_ID,
        until="2099-06-30",
        scanner=scanner,
        repo_root=tmp_path,
    )

    lines = ts_file.read_text(encoding="utf-8").splitlines()
    assert f"// atdd:suppress({_RULE_ID}) UNTIL=2099-06-30" in lines[1]
    assert result.edited_count == 1
    assert ts_file in result.files_touched


# ---------------------------------------------------------------------------
# acc:govern-lifecycle:E013-UNIT-004
# CLI suppress backfill exits 0 and prints punch list
# ---------------------------------------------------------------------------

def test_cli_suppress_backfill_exits_zero(tmp_path: Path, capsys):
    """E013-UNIT-004: atdd suppress backfill exits 0 with empty punch list."""
    from atdd.coach.commands.suppress import run_suppress_backfill

    def _empty_scanner(repo_root: Path) -> Tuple[int, List[Violation]]:  # noqa: ARG001
        return 0, []

    rc = run_suppress_backfill(
        rule_id=_RULE_ID,
        until="2099-01-01",
        repo_root=tmp_path,
        _scanner_override=_empty_scanner,
    )

    assert rc == 0
    captured = capsys.readouterr()
    assert "edited" in captured.out.lower() or "skipped" in captured.out.lower()


# ---------------------------------------------------------------------------
# acc:govern-lifecycle:E013-UNIT-005
# Unknown rule_id exits non-zero
# ---------------------------------------------------------------------------

def test_unknown_rule_exits_nonzero(tmp_path: Path, capsys):
    """E013-UNIT-005: unknown rule_id prints clear message and returns 1."""
    from atdd.coach.commands.suppress import run_suppress_backfill

    rc = run_suppress_backfill(
        rule_id="unknown.rule.id",
        until="2099-01-01",
        repo_root=tmp_path,
    )

    assert rc == 1
    captured = capsys.readouterr()
    output = (captured.out + captured.err).lower()
    assert "unknown" in output or "not supported" in output or "no scanner" in output


# ---------------------------------------------------------------------------
# acc:govern-lifecycle:E013-UNIT-006
# check_orphaned_baseline_keys warns on integer-count keys
# ---------------------------------------------------------------------------

def test_orphaned_baseline_warning_emitted(tmp_path: Path):
    """E013-UNIT-006: integer-count keys in coder.yaml generate one warning each."""
    from atdd.coach.commands.suppress import check_orphaned_baseline_keys

    baselines_dir = tmp_path / ".atdd" / "baselines"
    baselines_dir.mkdir(parents=True)
    (baselines_dir / "coder.yaml").write_text(
        "silent_exception_swallowing_python: 161\n"
        "some_other_string_key: foo\n",
        encoding="utf-8",
    )

    warnings = check_orphaned_baseline_keys(repo_root=tmp_path)

    assert len(warnings) == 1, f"Expected 1 warning, got {len(warnings)}: {warnings}"
    assert "orphaned-baseline-key" in warnings[0]
    assert "silent_exception_swallowing_python" in warnings[0]
    assert "substrate spec v12" in warnings[0]


# ---------------------------------------------------------------------------
# acc:govern-lifecycle:E013-UNIT-007
# check_orphaned_baseline_keys returns empty list when file absent
# ---------------------------------------------------------------------------

def test_no_coder_yaml_returns_empty(tmp_path: Path):
    """E013-UNIT-007: missing .atdd/baselines/coder.yaml → empty warning list."""
    from atdd.coach.commands.suppress import check_orphaned_baseline_keys

    warnings = check_orphaned_baseline_keys(repo_root=tmp_path)

    assert warnings == []


# ---------------------------------------------------------------------------
# acc:govern-lifecycle:E013-SMOKE-001
# End-to-end: real scanner + real file → violations suppressed
# ---------------------------------------------------------------------------

@pytest.mark.smoke
def test_backfill_on_real_fixture_suppresses_violations(tmp_path: Path):
    """E013-SMOKE-001: real scanner + real fixture file → all violations suppressed."""
    from atdd.coach.commands.suppress import suppress_backfill, BackfillResult
    from atdd.coder.validators.test_no_silent_exception_swallowing_python import (
        detect_silent_swallows,
    )
    from atdd.coach.validators._violation import Violation
    from atdd.coach.utils.suppression_scanner import is_suppressed

    fixture = tmp_path / "fixture.py"
    fixture.write_text(
        "def handle():\n"
        "    try:\n"
        "        risky()\n"
        "    except Exception:\n"
        "        pass\n",
        encoding="utf-8",
    )

    # Verify the fixture actually has a violation before backfill
    violations_before = detect_silent_swallows(fixture)
    assert violations_before, "Fixture must produce at least one violation"

    def real_scanner(repo_root: Path) -> tuple[int, list[Violation]]:
        vs = detect_silent_swallows(fixture)
        return len(vs), vs

    result: BackfillResult = suppress_backfill(
        rule_id=_RULE_ID,
        until="2099-01-01",
        scanner=real_scanner,
        repo_root=tmp_path,
    )

    assert result.edited_count >= 1

    # Second run must be a no-op
    result2: BackfillResult = suppress_backfill(
        rule_id=_RULE_ID,
        until="2099-01-01",
        scanner=real_scanner,
        repo_root=tmp_path,
    )
    assert result2.edited_count == 0

    # After backfill, every originally-flagged line has the suppress marker
    lines = fixture.read_text(encoding="utf-8").splitlines()
    for v in violations_before:
        _, lineno_str = v.location.rsplit(":", 1)
        lineno = int(lineno_str) - 1  # 0-based
        assert is_suppressed(lines[lineno], _RULE_ID), (
            f"Line {lineno + 1} was not suppressed: {lines[lineno]!r}"
        )
