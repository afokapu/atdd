# Acceptance: acc:govern-lifecycle:E017-SMOKE-001-docs-models-md-has-valid-structure
# Acceptance: acc:govern-lifecycle:E017-SMOKE-002-atdd-manifest-backfill-cli-wired
"""Smoke/integration tests for docs/MODELS.md structure and atdd manifest backfill CLI (#664).

These tests verify against the real filesystem and the cli.py source tree. They
do not require network access and have no side effects.

The installed atdd binary may lag the development tree, so CLI-wiring tests
read src/atdd/cli.py directly — following the pattern established by E012-SMOKE-002
in test_e012_smoke_pre_commit_manifest_exception.py.
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]

REPO_ROOT = Path(__file__).resolve().parents[5]
DOCS_MODELS_MD = REPO_ROOT / "docs" / "MODELS.md"
CLI_SOURCE = REPO_ROOT / "src" / "atdd" / "cli.py"


# ---------------------------------------------------------------------------
# E017-SMOKE-001 — docs/MODELS.md has valid markdown structure
# ---------------------------------------------------------------------------

class TestDocsModelsMdStructure:
    """docs/MODELS.md must have a valid markdown structure."""

    def test_starts_with_h1_heading(self) -> None:
        """E017-SMOKE-001: docs/MODELS.md must start with a level-1 heading."""
        assert DOCS_MODELS_MD.exists(), "docs/MODELS.md does not exist"
        content = DOCS_MODELS_MD.read_text()
        lines = content.splitlines()
        assert lines, "docs/MODELS.md is empty"
        assert lines[0].startswith("# "), (
            "docs/MODELS.md must start with a level-1 heading (# ...)"
        )

    def test_contains_markdown_table(self) -> None:
        """E017-SMOKE-001: docs/MODELS.md must contain at least one markdown table."""
        assert DOCS_MODELS_MD.exists(), "docs/MODELS.md does not exist"
        content = DOCS_MODELS_MD.read_text()
        table_lines = [l for l in content.splitlines() if l.strip().startswith("|")]
        assert len(table_lines) >= 2, (
            "docs/MODELS.md must contain at least one markdown table "
            "(pipe-delimited rows) listing adapter IDs"
        )

    def test_contains_env_var_section(self) -> None:
        """E017-SMOKE-001: docs/MODELS.md must have an environment variable section."""
        assert DOCS_MODELS_MD.exists(), "docs/MODELS.md does not exist"
        content = DOCS_MODELS_MD.read_text().lower()
        assert "env" in content or "environment" in content or "api_key" in content, (
            "docs/MODELS.md must have an environment variable or configuration section"
        )

    def test_contains_extension_section(self) -> None:
        """E017-SMOKE-001: docs/MODELS.md must have an extension/adapter registration guide."""
        assert DOCS_MODELS_MD.exists(), "docs/MODELS.md does not exist"
        content = DOCS_MODELS_MD.read_text().lower()
        assert any(kw in content for kw in ("extend", "add", "register", "new adapter")), (
            "docs/MODELS.md must include a guide for adding new adapters"
        )


# ---------------------------------------------------------------------------
# E017-SMOKE-002 — atdd manifest backfill CLI wired
# ---------------------------------------------------------------------------

class TestManifestBackfillCLIWired:
    """cli.py must register a manifest subparser with a backfill subcommand.

    The installed atdd binary may lag the local source tree, so we read
    src/atdd/cli.py directly — the same approach used by E012-SMOKE-002.
    """

    def test_cli_source_has_manifest_subparser(self) -> None:
        """E017-SMOKE-002: cli.py must register a 'manifest' subparser."""
        assert CLI_SOURCE.exists(), f"cli.py not found at {CLI_SOURCE}"
        content = CLI_SOURCE.read_text()
        assert '"manifest"' in content or "'manifest'" in content, (
            "cli.py must register 'manifest' as a subparser"
        )

    def test_cli_source_has_backfill_subcommand(self) -> None:
        """E017-SMOKE-002: cli.py must register 'backfill' under the manifest subparser."""
        assert CLI_SOURCE.exists(), f"cli.py not found at {CLI_SOURCE}"
        content = CLI_SOURCE.read_text()
        assert "backfill" in content, (
            "cli.py must register 'backfill' as a manifest subcommand"
        )

    def test_cli_source_manifest_backfill_calls_reconcile(self) -> None:
        """E017-SMOKE-002: The manifest backfill dispatch in cli.py must call manager.reconcile()."""
        assert CLI_SOURCE.exists(), f"cli.py not found at {CLI_SOURCE}"
        content = CLI_SOURCE.read_text()
        assert "manager.reconcile()" in content, (
            "cli.py must call manager.reconcile() from the manifest backfill dispatch block"
        )

    def test_issue_manager_has_reconcile_method(self) -> None:
        """E017-SMOKE-002: IssueManager must expose reconcile() after import."""
        from atdd.coach.commands.issue import IssueManager
        assert hasattr(IssueManager, "reconcile"), (
            "IssueManager must have reconcile() method"
        )
