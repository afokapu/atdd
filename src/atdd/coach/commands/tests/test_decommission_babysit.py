"""RED tests for decommissioning `atdd babysit` (issue #532, WMBT E002).

AC-UNIT-001: stub prints migration message and exits non-zero.
AC-UNIT-002: every absorbed babysit capability resolves to an atdd observer
             subcommand or observer rule (reverse-mapping verification).

These tests will FAIL until GREEN replaces commands/babysit.py with a stub
and moves the original implementation to commands/_archived/babysit.py.

URNs:
  acc:discover-and-decommission:E002-UNIT-001-babysit-stub-prints-migration-message
  acc:discover-and-decommission:E002-UNIT-002-babysit-machinery-reachable-via-coach-and-observer
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
    "atdd babysit has been removed in coach v9. "
    "Use 'atdd observer status' (dashboard), "
    "'atdd observer aggregate-approve' (batch approve), "
    "or 'atdd coach' (end-to-end) "
    "per atdd-coach-spec-v9.md §0.2."
)

_REPO_ROOT = Path(__file__).resolve().parents[5]  # repo root


class TestBabysitStub:
    """commands/babysit.py must be a stub that prints the migration message
    and exits non-zero without executing any babysit machinery."""

    def test_stub_no_babysit_machinery(self):
        """The stub module must NOT expose babysit internals.

        RED: fails because current babysit.py has all the machinery.
        GREEN: passes once the stub replaces the implementation.
        """
        import atdd.coach.commands.babysit as mod

        assert not hasattr(mod, "BashPattern"), (
            "BashPattern must not be exposed — it belongs in the archive"
        )
        assert not hasattr(mod, "_load_bash_patterns"), (
            "_load_bash_patterns must not be exposed — it belongs in the archive"
        )
        assert not hasattr(mod, "classify_prompt"), (
            "classify_prompt must not be exposed — it belongs in the archive"
        )
        assert not hasattr(mod, "aggregate_approve"), (
            "aggregate_approve must not be exposed — it belongs in the archive"
        )
        assert not hasattr(mod, "correct_naming_drift"), (
            "correct_naming_drift must not be exposed — it belongs in the archive"
        )
        assert not hasattr(mod, "correct_layout_drift"), (
            "correct_layout_drift must not be exposed — it belongs in the archive"
        )
        assert not hasattr(mod, "detect_violation"), (
            "detect_violation must not be exposed — it belongs in the archive"
        )
        assert not hasattr(mod, "process_workspace"), (
            "process_workspace must not be exposed — it belongs in the archive"
        )
        assert not hasattr(mod, "_screen_hash"), (
            "_screen_hash must not be exposed — it belongs in the archive"
        )
        assert not hasattr(mod, "_render_dashboard"), (
            "_render_dashboard must not be exposed — it belongs in the archive"
        )
        assert not hasattr(mod, "SurfaceRow"), (
            "SurfaceRow must not be exposed — it belongs in the archive"
        )

    def test_stub_has_migration_message_constant(self):
        """The stub module must export MIGRATION_MESSAGE.

        RED: fails because current babysit.py has no MIGRATION_MESSAGE.
        GREEN: passes once the stub is installed.
        """
        import atdd.coach.commands.babysit as mod

        assert hasattr(mod, "MIGRATION_MESSAGE"), (
            "Stub must expose MIGRATION_MESSAGE constant"
        )
        assert MIGRATION_MESSAGE in mod.MIGRATION_MESSAGE, (
            f"MIGRATION_MESSAGE must equal: {MIGRATION_MESSAGE!r}"
        )

    def test_stub_cli_entry_exits_nonzero(self):
        """atdd babysit exits non-zero and prints migration message.

        RED: exits non-zero (MultiplexerError from full implementation) but
             prints the wrong message. Test checks both conditions together.
        GREEN: stub exits 1 and prints the migration message.
        """
        import os

        env = {**os.environ, "PYTHONPATH": str(_REPO_ROOT / "src")}
        result = subprocess.run(
            [sys.executable, "-m", "atdd", "babysit", "--once"],
            capture_output=True,
            text=True,
            timeout=15,
            env=env,
        )
        assert result.returncode != 0, (
            f"atdd babysit must exit non-zero; got {result.returncode}"
        )
        combined = result.stdout + result.stderr
        assert MIGRATION_MESSAGE in combined, (
            f"atdd babysit must print migration message.\n"
            f"stdout: {result.stdout!r}\n"
            f"stderr: {result.stderr!r}"
        )

    def test_archived_module_has_machinery(self):
        """The archived module at _archived/babysit.py must preserve the
        original implementation for parity-test reuse.

        RED: fails with ImportError because _archived/babysit.py doesn't exist.
        GREEN: passes once the original babysit.py is moved there.
        """
        import atdd.coach.commands._archived.babysit as archived

        assert hasattr(archived, "aggregate_approve")
        assert hasattr(archived, "classify_prompt")
        assert hasattr(archived, "_render_dashboard")


# ---------------------------------------------------------------------------
# AC-UNIT-002: reverse mapping — every absorbed capability reachable via observer
# ---------------------------------------------------------------------------

class TestBabysitReverseMapping:
    """Every absorbed babysit capability (per spec §0.2) must resolve to an
    atdd observer subcommand or observer rule. Replaced capabilities
    (workspace polling, phase-cache-via-labels) intentionally have no parity
    test per spec §0.2."""

    RULES_DIR = _REPO_ROOT / ".atdd" / "observer" / "rules"

    def _rule_exists(self, rule_slug: str) -> bool:
        return (self.RULES_DIR / f"{rule_slug}.yaml").exists()

    def test_token_count_alerting_maps_to_rule_06(self):
        """Token-count alerting → observer rule 06-token-threshold."""
        assert self._rule_exists("06-token-threshold"), (
            "Observer rule 06-token-threshold.yaml must exist — "
            "it absorbs babysit's token-count alerting capability."
        )

    def test_bash_auto_approval_maps_to_rule_13(self):
        """Bash auto-approval → observer rule 13-bash-auto-approve."""
        assert self._rule_exists("13-bash-auto-approve"), (
            "Observer rule 13-bash-auto-approve.yaml must exist — "
            "it absorbs babysit's bash auto-approval capability."
        )

    def test_aggregate_approval_maps_to_observer_subcommand(self):
        """Aggregate approval → atdd observer aggregate-approve."""
        from atdd.coach.commands.observer import cmd_aggregate_approve

        assert callable(cmd_aggregate_approve), (
            "observer.cmd_aggregate_approve must be callable — "
            "it absorbs babysit's aggregate-approval capability."
        )

    def test_naming_drift_maps_to_rule_14(self):
        """Naming drift correction → observer rule 14-canonical-naming-drift."""
        assert self._rule_exists("14-canonical-naming-drift"), (
            "Observer rule 14-canonical-naming-drift.yaml must exist — "
            "it absorbs babysit's naming-drift correction capability."
        )

    def test_layout_drift_maps_to_rule_15(self):
        """Layout drift correction → observer rule 15-layout-drift."""
        assert self._rule_exists("15-layout-drift"), (
            "Observer rule 15-layout-drift.yaml must exist — "
            "it absorbs babysit's layout-drift correction capability."
        )

    def test_violation_detection_maps_to_rules_04_and_16(self):
        """Violation detection → observer rules 04-out-of-scope-edit and
        16-smoke-skip."""
        assert self._rule_exists("04-out-of-scope-edit"), (
            "Observer rule 04-out-of-scope-edit.yaml must exist — "
            "it absorbs babysit's out-of-scope-edit detection."
        )
        assert self._rule_exists("16-smoke-skip"), (
            "Observer rule 16-smoke-skip.yaml must exist — "
            "it absorbs babysit's smoke-skip detection."
        )

    def test_dashboard_maps_to_observer_status(self):
        """Dashboard → atdd observer status."""
        from atdd.coach.commands.observer import cmd_status

        assert callable(cmd_status), (
            "observer.cmd_status must be callable — "
            "it absorbs babysit's _render_dashboard capability."
        )

    def test_workspace_polling_is_replaced_not_absorbed(self):
        """process_workspace polling is replaced by event-driven runtime
        watchers — no polling parity test by design (spec §0.2)."""
        from atdd.coach.commands import runtime_watcher

        assert hasattr(runtime_watcher, "RuntimeWatcher") or callable(
            getattr(runtime_watcher, "run", None)
        ), (
            "runtime_watcher module must exist — it replaces "
            "babysit's process_workspace polling."
        )

    def test_phase_cache_is_replaced_by_state_machine(self):
        """_fetch_phase_cache / _phase_from_labels is replaced by the coach
        state machine — no label-polling parity test by design (spec §0.2)."""
        from atdd.coach.commands import issue_lifecycle

        assert hasattr(issue_lifecycle, "IssueLifecycle"), (
            "issue_lifecycle module must manage phase state — it replaces "
            "babysit's _fetch_phase_cache/label-polling capability."
        )


# ---------------------------------------------------------------------------
# Zero non-archive callsites
# ---------------------------------------------------------------------------

class TestNoInternalCallsites:
    """Grep across the repository for non-archive invocations of the original
    babysit implementation. Assert zero hits outside allowed paths."""

    EXCLUDED_PREFIXES = (
        "commands/_archived/",
        "commands/tests/test_babysit",
        "commands/tests/test_decommission_babysit",
        "commands/tests/test_e001_unit_002_parity_with_babysit",
        "commands/tests/test_e001_unit_001_observer_aggregate_approve",
        "commands/tests/test_l001_unit_002_parity_with_babysit",
        "commands/tests/test_m002_unit_003_babysit_parity",
        "tests/integration/",
    )

    def _collect_py_files(self) -> list[tuple[Path, str]]:
        src = _REPO_ROOT / "src"
        tests = _REPO_ROOT / "tests"
        files: list[tuple[Path, str]] = []
        for base in (src, tests):
            if not base.exists():
                continue
            for p in base.rglob("*.py"):
                rel = str(p.relative_to(_REPO_ROOT))
                files.append((p, rel))
        return files

    def test_zero_archived_imports_outside_allowed(self):
        """No shipped code imports _archived.babysit except parity tests
        and observer rule modules (the legitimate absorption consumers).

        This test passes in both RED and GREEN, documenting the callsite invariant.
        """
        hits: list[str] = []
        allowed = (
            "commands/_archived/",
            "commands/tests/",
            "observer_rules/",  # absorption consumers per spec §0.2
            "tests/integration/",
        )
        for p, rel in self._collect_py_files():
            if any(a in rel for a in allowed):
                continue
            text = p.read_text(errors="replace")
            if "_archived.babysit" in text or "_archived import babysit" in text:
                for i, line in enumerate(text.splitlines(), 1):
                    if "_archived" in line and "babysit" in line:
                        hits.append(f"{rel}:{i}: {line.strip()}")
        assert hits == [], (
            "Found _archived.babysit imports outside allowed consumers:\n"
            + "\n".join(hits)
        )
