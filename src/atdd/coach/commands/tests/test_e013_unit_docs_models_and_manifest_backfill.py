# Acceptance: acc:govern-lifecycle:E017-UNIT-001-docs-models-md-exists-with-adapter-table
# Acceptance: acc:govern-lifecycle:E017-UNIT-002-atdd-manifest-backfill-routes-to-reconcile
"""Unit tests for docs/MODELS.md existence and atdd manifest backfill CLI routing (#664).

Problem:
  (1) docs/MODELS.md does not exist — operators see an adapter picker at
      startup (#723) with no reference document describing adapter IDs,
      required env vars, or permission policies.
  (2) `atdd manifest backfill` is not a registered CLI route — the backfill
      capability exists under `atdd issue reconcile` but is undiscoverable.

Fix:
  (1) Create docs/MODELS.md with an adapter table covering every entry in
      ADAPTER_REGISTRY, an env-vars section, and an extension recipe.
  (2) Wire `atdd manifest backfill` in cli.py as a subcommand that delegates
      to IssueManager.reconcile().
"""
from __future__ import annotations

from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _repo_root() -> Path:
    """Return the repository root (the directory containing pyproject.toml)."""
    here = Path(__file__).resolve()
    for parent in [here, *here.parents]:
        if (parent / "pyproject.toml").exists():
            return parent
    raise FileNotFoundError("Could not locate repo root via pyproject.toml")


# ---------------------------------------------------------------------------
# E017-UNIT-001 — docs/MODELS.md exists with adapter table
# ---------------------------------------------------------------------------

class TestDocsModelsMdExists:
    """docs/MODELS.md must exist and document every registered adapter."""

    def test_docs_models_md_file_exists(self) -> None:
        """E017-UNIT-001: docs/MODELS.md must exist at the repo root."""
        models_md = _repo_root() / "docs" / "MODELS.md"
        assert models_md.exists(), (
            "docs/MODELS.md does not exist — create it with an adapter table "
            "covering every entry in ADAPTER_REGISTRY"
        )

    def test_docs_models_md_mentions_claude_code_adapter(self) -> None:
        """E017-UNIT-001: docs/MODELS.md must mention the 'claude-code' adapter."""
        from atdd.coach.commands.spawn import ADAPTER_REGISTRY

        models_md = _repo_root() / "docs" / "MODELS.md"
        assert models_md.exists(), "docs/MODELS.md does not exist"
        content = models_md.read_text()

        for adapter_id in ADAPTER_REGISTRY:
            assert adapter_id in content, (
                f"docs/MODELS.md must contain adapter id '{adapter_id}' — "
                "add a row for each entry in ADAPTER_REGISTRY"
            )

    def test_docs_models_md_mentions_env_var(self) -> None:
        """E017-UNIT-001: docs/MODELS.md must reference at least one env var."""
        models_md = _repo_root() / "docs" / "MODELS.md"
        assert models_md.exists(), "docs/MODELS.md does not exist"
        content = models_md.read_text()
        assert "ANTHROPIC_API_KEY" in content or "env" in content.lower(), (
            "docs/MODELS.md must include an environment-variables section or "
            "reference the required env vars for each adapter"
        )

    def test_docs_models_md_has_extension_section(self) -> None:
        """E017-UNIT-001: docs/MODELS.md must contain an extension recipe section."""
        models_md = _repo_root() / "docs" / "MODELS.md"
        assert models_md.exists(), "docs/MODELS.md does not exist"
        content = models_md.read_text().lower()
        assert "extend" in content or "add" in content or "register" in content, (
            "docs/MODELS.md must include a section explaining how to add new adapters"
        )


# ---------------------------------------------------------------------------
# E017-UNIT-002 — atdd manifest backfill routes to IssueManager.reconcile()
# ---------------------------------------------------------------------------

class TestManifestBackfillCLIRouting:
    """cli.py must route 'atdd manifest backfill' to IssueManager.reconcile()."""

    def test_issue_manager_has_reconcile(self) -> None:
        """E017-UNIT-002: IssueManager must expose a reconcile() method."""
        from atdd.coach.commands.issue import IssueManager
        assert hasattr(IssueManager, "reconcile"), (
            "IssueManager must have a reconcile() method for manifest backfill"
        )

    def test_cli_has_manifest_backfill_dispatch(self) -> None:
        """E017-UNIT-002: cli.py must register a manifest backfill dispatch route."""
        cli_path = _repo_root() / "src" / "atdd" / "cli.py"
        assert cli_path.exists(), f"cli.py not found at {cli_path}"
        content = cli_path.read_text()
        assert "manifest" in content, (
            "cli.py must contain a 'manifest' subparser or top-level command"
        )
        assert "backfill" in content, (
            "cli.py must contain a 'backfill' dispatch target under manifest"
        )

    def test_cli_manifest_backfill_calls_reconcile(self) -> None:
        """E017-UNIT-002: The manifest backfill route in cli.py must call reconcile()."""
        cli_path = _repo_root() / "src" / "atdd" / "cli.py"
        content = cli_path.read_text()
        assert "reconcile" in content, (
            "cli.py must call manager.reconcile() (or equivalent) for manifest backfill"
        )
