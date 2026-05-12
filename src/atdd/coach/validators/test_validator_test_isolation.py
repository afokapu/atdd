# URN: test:integration-hardening:validator-test-isolation:Y002-UNIT-001-isolation-gate
# Acceptance: acc:integration-hardening:Y002-UNIT-001-no-phantom-commits
# Acceptance: acc:integration-hardening:Y002-UNIT-002-core-bare-unchanged
# Acceptance: acc:integration-hardening:Y002-UNIT-003-guard-fixture-registered
# Acceptance: acc:integration-hardening:Y002-UNIT-004-post-commit-hook-enabled
# WMBT: wmbt:integration-hardening:Y001
# Phase: GREEN
# Layer: coach.validator

"""Validator test-isolation regression gate (issue #619).

Verifies that:
  GT-001/GT-002 — the session-scoped integrity guard is present in conftest
                  so ``atdd validate coach`` cannot silently accumulate
                  phantom commits or flip ``core.bare``.
  GT-003         — the guard fixture is session-scoped and autouse so it
                  fires for every coach-validator run.
  GT-004         — the post-commit hook is installed in ``.atdd/hooks/``
                  and matches the template, so blast-radius validation
                  can be re-enabled safely.
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]

_PKG_DIR = Path(__file__).resolve().parent.parent          # src/atdd/coach
_REPO_ROOT = _PKG_DIR.parent.parent.parent                 # repo root
_VALIDATORS_DIR = _PKG_DIR / "validators"
_TEMPLATE_DIR = _PKG_DIR / "templates" / "hooks"
_INSTALLED_HOOKS_DIR = _REPO_ROOT / ".atdd" / "hooks"


# ---------------------------------------------------------------------------
# GT-001 / GT-002 / GT-003 — guard fixture in conftest
# ---------------------------------------------------------------------------


def test_worktree_integrity_guard_exists_in_conftest():
    """GT-003: ``_worktree_integrity_guard`` is defined in the validators conftest.

    The guard is a session-scoped autouse fixture that snapshots HEAD and
    core.bare before the test session and asserts they are unchanged after,
    catching any future test that accidentally commits against the live
    worktree (issue #619 incident).
    """
    conftest = _VALIDATORS_DIR / "conftest.py"
    assert conftest.is_file(), f"conftest.py not found at {conftest}"

    content = conftest.read_text(encoding="utf-8")
    assert "_worktree_integrity_guard" in content, (
        "conftest.py is missing the ``_worktree_integrity_guard`` session "
        "fixture.\n"
        "Fix: add a session-scoped autouse fixture that snapshots git HEAD "
        "and core.bare before the session and asserts they are unchanged "
        "after. See issue #619 for the incident description."
    )


def test_worktree_integrity_guard_is_session_scoped_autouse():
    """GT-003: the guard fixture must be both session-scoped and autouse.

    Neither attribute alone is sufficient: session-scoped-but-not-autouse
    means it only fires when explicitly requested; autouse-but-not-session
    means per-test overhead and loses the before/after comparison across
    the full run.
    """
    conftest = _VALIDATORS_DIR / "conftest.py"
    content = conftest.read_text(encoding="utf-8")

    assert 'scope="session"' in content, (
        "``_worktree_integrity_guard`` must use ``scope=\"session\"`` so the "
        "snapshot spans the entire validator run, not individual tests."
    )
    assert "autouse=True" in content, (
        "``_worktree_integrity_guard`` must use ``autouse=True`` so it fires "
        "unconditionally without being listed in test function signatures."
    )


# ---------------------------------------------------------------------------
# GT-004 — post-commit hook installed
# ---------------------------------------------------------------------------


def test_post_commit_hook_installed_in_atdd_hooks():
    """GT-004: ``.atdd/hooks/post-commit`` must exist.

    The hook was disabled in main (renamed to ``.post-commit.disabled``)
    after the incident in PR #618. Re-enabling it requires the file to be
    present in the hooks directory that git's ``hooksPath`` points to.
    """
    hook = _INSTALLED_HOOKS_DIR / "post-commit"
    assert hook.is_file(), (
        f"``.atdd/hooks/post-commit`` is missing.\n"
        f"Expected at: {hook}\n"
        "Fix: cp src/atdd/coach/templates/hooks/post-commit "
        ".atdd/hooks/post-commit"
    )


def test_post_commit_hook_matches_template():
    """GT-004: installed post-commit hook must match the committed template.

    The template at ``src/atdd/coach/templates/hooks/post-commit`` is the
    source of truth. Any local divergence would go unnoticed in review.
    """
    template = _TEMPLATE_DIR / "post-commit"
    if not template.is_file():
        pytest.skip(f"template not found at {template}")

    hook = _INSTALLED_HOOKS_DIR / "post-commit"
    if not hook.is_file():
        pytest.skip("post-commit hook not installed — GT-004 covers the presence check")

    assert hook.read_text(encoding="utf-8") == template.read_text(encoding="utf-8"), (
        f"``.atdd/hooks/post-commit`` differs from the template.\n"
        f"Template: {template}\n"
        f"Installed: {hook}\n"
        "Fix: cp src/atdd/coach/templates/hooks/post-commit .atdd/hooks/post-commit"
    )
