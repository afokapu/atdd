"""
Phase 1 unit tests for ``atdd pr`` base-branch validation (issue #477).

The CLI guard at src/atdd/coach/commands/pr.py:~555 must:
  1. Accept the default base (implicit and explicit).
  2. Reject any non-default base unless ``--force`` is passed.
  3. Print a runnable structured Fix hint on rejection (#467 contract C1-C4).
  4. Honor a ``--force`` override with a ``::warning::`` log line.
  5. Resolve the default branch via the helper at
     ``src/atdd/coach/utils/default_branch.py`` (config → gh → "main").

These tests stub out the network/subprocess seam so the CLI guard's
control flow is exercised in isolation. Cross-coordinated with #478
on the shared default-branch helper.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from atdd.coach.commands.pr import PRManager


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def manager(tmp_path: Path) -> PRManager:
    """A PRManager rooted at an isolated tmp dir (no real .atdd config)."""
    (tmp_path / ".atdd").mkdir()
    (tmp_path / ".atdd" / "config.yaml").write_text(
        "github:\n"
        "  repo: example/repo\n"
        "  default_branch: main\n",
        encoding="utf-8",
    )
    (tmp_path / ".atdd" / "manifest.yaml").write_text("sessions: []\n", encoding="utf-8")
    return PRManager(target_dir=tmp_path)


def _patch_common(monkeypatch, branch: str = "feat/477-pr-base-validation"):
    """Stub the network/git seams so only the validation block runs."""
    from atdd.coach.commands import pr as pr_module

    monkeypatch.setattr(PRManager, "_detect_branch", lambda self: branch)
    monkeypatch.setattr(PRManager, "_existing_pr_for_branch", lambda self, b: None)
    monkeypatch.setattr(PRManager, "_merged_pr_for_branch", lambda self, b: None)
    monkeypatch.setattr(
        PRManager, "_fetch_issue",
        lambda self, n: {"title": "Test", "number": n, "labels": []},
    )
    monkeypatch.setattr(PRManager, "_find_issue_in_manifest", lambda self, n: None)
    monkeypatch.setattr(PRManager, "_fetch_sub_issues", lambda self, n: [])

    class _OK:
        returncode = 0
        stdout = "https://github.com/example/repo/pull/999"
        stderr = ""

    monkeypatch.setattr(pr_module.subprocess, "run", lambda *a, **kw: _OK())


# ---------------------------------------------------------------------------
# Fixture 1: default base implicit — accepted
# ---------------------------------------------------------------------------


def test_default_base_implicit_is_accepted(manager, monkeypatch, capsys):
    """``atdd pr <N>`` with no --base resolves default and proceeds."""
    _patch_common(monkeypatch)
    rc = manager.pr(issue_number=477)
    assert rc == 0
    out = capsys.readouterr().out
    assert "Refusing to create PR" not in out


# ---------------------------------------------------------------------------
# Fixture 2: explicit default base — accepted
# ---------------------------------------------------------------------------


def test_explicit_default_base_is_accepted(manager, monkeypatch, capsys):
    """``atdd pr <N> --base main`` (matches default) proceeds without warning."""
    _patch_common(monkeypatch)
    rc = manager.pr(issue_number=477, base="main")
    assert rc == 0
    out = capsys.readouterr().out
    assert "Refusing to create PR" not in out
    assert "::warning::" not in out


# ---------------------------------------------------------------------------
# Fixture 3: non-default base without --force — rejected
# ---------------------------------------------------------------------------


def test_non_default_base_without_force_is_rejected(manager, monkeypatch, capsys):
    """A non-default base produces a structured rejection (#467 C1-C4 hint)."""
    _patch_common(monkeypatch)
    rc = manager.pr(issue_number=477, base="feat/some-other-branch")
    assert rc == 1
    out = capsys.readouterr().out
    assert "Refusing to create PR" in out
    # Numbered Fix steps (C3 + C4 contract)
    assert "1. Re-run with the default base" in out
    assert "2. Or pass the default explicitly" in out
    assert "3. Override only for legitimate" in out
    # Runnable as printed (C4): the issue number is resolved
    assert "atdd pr 477" in out
    # Citation back to the lived incident
    assert "#477" in out


# ---------------------------------------------------------------------------
# Fixture 4: non-default base with --force — accepted with ::warning::
# ---------------------------------------------------------------------------


def test_force_override_accepted_with_warning(manager, monkeypatch, capsys):
    """``--force`` lets a non-default base through but emits a ::warning::."""
    _patch_common(monkeypatch)
    rc = manager.pr(
        issue_number=477,
        base="release/v3-train",
        force=True,
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "::warning::" in out
    assert "release/v3-train" in out
    assert "Refusing to create PR" not in out


# ---------------------------------------------------------------------------
# Fixture 5: default-branch helper falls back through resolution chain
# ---------------------------------------------------------------------------


def test_default_branch_lookup_falls_back_through_chain(tmp_path, monkeypatch):
    """Helper: config absent → gh CLI → 'main' literal fallback.

    Exercises all three legs of the resolver shared with #478.
    """
    from atdd.coach.utils import default_branch as helper

    # Leg 1: config provides the answer.
    (tmp_path / ".atdd").mkdir()
    cfg = tmp_path / ".atdd" / "config.yaml"
    cfg.write_text("github:\n  default_branch: trunk\n", encoding="utf-8")
    assert helper.resolve_default_branch(tmp_path) == "trunk"

    # Leg 2: config absent, gh CLI returns the default.
    cfg.unlink()
    class _GhOK:
        returncode = 0
        stdout = "master\n"
        stderr = ""
    with patch.object(helper.subprocess, "run", return_value=_GhOK()):
        assert helper.resolve_default_branch(tmp_path) == "master"

    # Leg 3: config absent + gh fails → "main" literal fallback.
    class _GhFail:
        returncode = 1
        stdout = ""
        stderr = "gh: not authenticated"
    with patch.object(helper.subprocess, "run", return_value=_GhFail()):
        assert helper.resolve_default_branch(tmp_path) == "main"
