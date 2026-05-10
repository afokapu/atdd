"""RED tests for decommissioning `atdd orchestrate` (issue #531, WMBT E001).

AC-UNIT-001: stub prints migration message and exits non-zero.
AC-UNIT-002: zero non-archive callsites of `atdd orchestrate` in shipped code.

These tests import from the stub (not yet created) and assert the
decommissioned surface. They will FAIL until GREEN replaces the module.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]

# ---------------------------------------------------------------------------
# AC-UNIT-001: stub prints migration message and exits non-zero
# ---------------------------------------------------------------------------

MIGRATION_MESSAGE = (
    "atdd orchestrate has been removed in coach v9. "
    "Use 'atdd coach <issue-numbers>' instead. "
    "Migration: every flag maps directly per atdd-coach-spec-v9.md §5.1."
)


class TestOrchestrateStub:
    """The stub at commands/orchestrate.py must print the migration message
    and exit non-zero without executing any orchestrate machinery."""

    def test_stub_run_returns_nonzero(self):
        from atdd.coach.commands.orchestrate import run

        with pytest.raises(SystemExit) as exc_info:
            run(issue_numbers=[1, 2, 3])
        assert exc_info.value.code != 0

    def test_stub_run_prints_migration_message(self, capsys):
        from atdd.coach.commands.orchestrate import run

        with pytest.raises(SystemExit):
            run(issue_numbers=[1])
        captured = capsys.readouterr()
        combined = captured.out + captured.err
        assert MIGRATION_MESSAGE in combined

    def test_stub_cli_entry_exits_nonzero(self):
        import os

        env = {**os.environ, "PYTHONPATH": str(_REPO_ROOT / "src")}
        result = subprocess.run(
            [sys.executable, "-m", "atdd", "orchestrate", "1"],
            capture_output=True,
            text=True,
            timeout=30,
            env=env,
        )
        assert result.returncode != 0
        combined = result.stdout + result.stderr
        assert MIGRATION_MESSAGE in combined

    def test_stub_no_orchestrate_machinery(self):
        """The stub module must NOT expose orchestrate internals."""
        import atdd.coach.commands.orchestrate as mod

        assert not hasattr(mod, "build_plan")
        assert not hasattr(mod, "compute_waves")
        assert not hasattr(mod, "PlannedIssue")
        assert not hasattr(mod, "load_state")
        assert not hasattr(mod, "save_state")
        assert not hasattr(mod, "_create_worktree")
        assert not hasattr(mod, "_remove_worktree")


# ---------------------------------------------------------------------------
# AC-UNIT-002: zero non-archive callsites
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[5]  # repo root


class TestNoInternalCallsites:
    """Grep across the repository for `atdd orchestrate` invocations and
    direct imports of the archived module. Assert zero non-excluded callsites."""

    EXCLUDED_PREFIXES = (
        "commands/_archived/",
        "commands/tests/test_orchestrate",
        "commands/tests/test_orchestrate_wave_walk",
        "commands/tests/test_orchestrate_ready_lifecycle",
        "commands/tests/test_orchestration_convention",
        "commands/tests/test_decommission_orchestrate",
        "tests/integration/test_orchestrate_coach_parity",
        "tests/integration/parity-fixtures/",
    )

    def _collect_py_files(self) -> list[Path]:
        src = _REPO_ROOT / "src"
        tests = _REPO_ROOT / "tests"
        files: list[Path] = []
        for base in (src, tests):
            if not base.exists():
                continue
            for p in base.rglob("*.py"):
                rel = p.relative_to(_REPO_ROOT)
                files.append((p, str(rel)))
        return files

    def test_zero_atdd_orchestrate_subprocess_calls(self):
        """No shipped code calls `atdd orchestrate` as a subprocess."""
        hits: list[str] = []
        for p, rel in self._collect_py_files():
            if any(excl in rel for excl in self.EXCLUDED_PREFIXES):
                continue
            text = p.read_text(errors="replace")
            if '"atdd"' in text and '"orchestrate"' in text:
                for i, line in enumerate(text.splitlines(), 1):
                    if '"atdd"' in line and '"orchestrate"' in line:
                        hits.append(f"{rel}:{i}: {line.strip()}")
        assert hits == [], (
            f"Found `atdd orchestrate` subprocess callsites in shipped code:\n"
            + "\n".join(hits)
        )

    def test_zero_archived_imports_outside_parity(self):
        """No shipped code imports from commands._archived.orchestrate
        except coach.py and two_phase_commit.py (absorbed consumers)."""
        hits: list[str] = []
        allowed = (
            "commands/coach.py",
            "commands/two_phase_commit.py",
            "commands/_archived/",
            "commands/tests/",
            "tests/integration/",
        )
        for p, rel in self._collect_py_files():
            if any(rel.endswith(a) or a in rel for a in allowed):
                continue
            text = p.read_text(errors="replace")
            if "_archived.orchestrate" in text:
                for i, line in enumerate(text.splitlines(), 1):
                    if "_archived.orchestrate" in line:
                        hits.append(f"{rel}:{i}: {line.strip()}")
        assert hits == [], (
            f"Found _archived.orchestrate imports outside allowed consumers:\n"
            + "\n".join(hits)
        )

    def test_convention_file_unchanged(self):
        """The orchestration convention file must still exist and resolve."""
        conv = _REPO_ROOT / "src/atdd/coach/conventions/orchestration.convention.yaml"
        assert conv.exists(), "orchestration.convention.yaml must be preserved"
        text = conv.read_text()
        assert "bind_rule" in text or "rules:" in text
