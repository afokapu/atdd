"""
E012: Worktree enforcement — hook template regression tests.

Validates that hook templates enforce branch-scoped protection for main/master
without path-prefix escape hatches. These are deterministic, offline tests that
read template file content and assert structural properties.

Run: PYTHONPATH=src python3 -m pytest -q src/atdd/coach/validators/test_worktree_enforcement.py -v
"""
import re
from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]

# --- Locate hook files ---

_PKG_DIR = Path(__file__).resolve().parent.parent  # src/atdd/coach
_TEMPLATE_DIR = _PKG_DIR / "templates" / "hooks"
_REPO_ROOT = _PKG_DIR.parent.parent.parent  # coach -> atdd -> src -> repo root
_INSTALLED_DIR = _REPO_ROOT / ".atdd" / "hooks"

_HOOK_NAMES = ("pre-commit", "pre-push", "pre-merge-commit")


def _read_hook(hook_dir: Path, name: str) -> str:
    """Read a hook file, skip test if missing."""
    path = hook_dir / name
    if not path.exists():
        pytest.skip(f"{path} not found")
    return path.read_text()


class TestPreCommitEnforcement:
    """E012: pre-commit blocks all commits on main/master unconditionally."""

    def test_pre_commit_blocks_all_on_main(self):
        """
        SPEC-SESSION-VAL-0080: pre-commit has no path-prefix filtering.

        Given: The pre-commit hook template
        When: Checking for path-scoped PROTECTED variable
        Then: No PROTECTED path list exists; hook blocks unconditionally on main
        """
        content = _read_hook(_TEMPLATE_DIR, "pre-commit")

        assert "PROTECTED=" not in content, (
            "\npre-commit template still contains a PROTECTED path list.\n"
            "Fix: Remove path-prefix filtering — block all commits on main/master.\n"
        )
        assert 'main|master' in content, (
            "\npre-commit template does not check for main/master branch.\n"
        )
        assert 'exit 1' in content, (
            "\npre-commit template does not exit non-zero to block commits.\n"
        )

    def test_pre_commit_has_ci_bypass(self):
        """
        SPEC-SESSION-VAL-0083a: pre-commit has CI bypass for ATDD_ALLOW_MAIN_COMMIT.

        Given: The pre-commit hook template
        When: Checking for CI bypass env var
        Then: ATDD_ALLOW_MAIN_COMMIT bypass is present
        """
        content = _read_hook(_TEMPLATE_DIR, "pre-commit")

        assert "ATDD_ALLOW_MAIN_COMMIT" in content, (
            "\npre-commit template missing CI bypass env var ATDD_ALLOW_MAIN_COMMIT.\n"
        )
        assert 'CI' in content, (
            "\npre-commit template missing CI env var check.\n"
        )


class TestPrePushEnforcement:
    """E012: pre-push blocks all pushes to main/master unconditionally."""

    def test_pre_push_blocks_all_on_main(self):
        """
        SPEC-SESSION-VAL-0081: pre-push has no path-prefix filtering for push blocking.

        Given: The pre-push hook template
        When: Checking for path-scoped PROTECTED variable used in push blocking
        Then: No PROTECTED path list exists for push blocking
        """
        content = _read_hook(_TEMPLATE_DIR, "pre-push")

        assert "PROTECTED=" not in content, (
            "\npre-push template still contains a PROTECTED path list.\n"
            "Fix: Remove path-prefix filtering — block all pushes to main/master.\n"
        )
        assert 'refs/heads/main' in content, (
            "\npre-push template does not check for refs/heads/main.\n"
        )
        assert 'exit 1' in content, (
            "\npre-push template does not exit non-zero to block pushes.\n"
        )

    def test_pre_push_has_ci_bypass(self):
        """
        SPEC-SESSION-VAL-0083b: pre-push has CI bypass for ATDD_ALLOW_MAIN_PUSH.

        Given: The pre-push hook template
        When: Checking for CI bypass env var
        Then: ATDD_ALLOW_MAIN_PUSH bypass is present
        """
        content = _read_hook(_TEMPLATE_DIR, "pre-push")

        assert "ATDD_ALLOW_MAIN_PUSH" in content, (
            "\npre-push template missing CI bypass env var ATDD_ALLOW_MAIN_PUSH.\n"
        )


class TestPreMergeCommitEnforcement:
    """E012: pre-merge-commit blocks merges into main/master."""

    def test_pre_merge_commit_blocks_on_main(self):
        """
        SPEC-SESSION-VAL-0082: pre-merge-commit blocks merges into main/master.

        Given: The pre-merge-commit hook template
        When: Checking for branch-scoped merge protection
        Then: Hook checks current branch and blocks on main/master
        """
        content = _read_hook(_TEMPLATE_DIR, "pre-merge-commit")

        assert 'main|master' in content, (
            "\npre-merge-commit template does not check for main/master branch.\n"
        )
        # Must have at least two exit 1 (one for version gate, one for merge block)
        exit_ones = [m.start() for m in re.finditer(r'exit 1', content)]
        assert len(exit_ones) >= 2, (
            f"\npre-merge-commit template has {len(exit_ones)} exit-1 points, expected >= 2.\n"
            "Fix: Add branch-scoped merge protection that exits non-zero on main.\n"
        )

    def test_pre_merge_commit_has_ci_bypass(self):
        """
        SPEC-SESSION-VAL-0083c: pre-merge-commit has CI bypass for ATDD_ALLOW_MAIN_MERGE.

        Given: The pre-merge-commit hook template
        When: Checking for CI bypass env var
        Then: ATDD_ALLOW_MAIN_MERGE bypass is present
        """
        content = _read_hook(_TEMPLATE_DIR, "pre-merge-commit")

        assert "ATDD_ALLOW_MAIN_MERGE" in content, (
            "\npre-merge-commit template missing CI bypass env var ATDD_ALLOW_MAIN_MERGE.\n"
        )


class TestInstalledHooksMatchTemplates:
    """E012: Installed hooks in .atdd/hooks/ must match templates."""

    @pytest.mark.parametrize("hook_name", _HOOK_NAMES)
    def test_installed_hooks_match_templates(self, hook_name):
        """
        SPEC-SESSION-VAL-0084: Installed hook matches its template.

        Given: A hook template and its installed counterpart
        When: Comparing file contents
        Then: They are identical
        """
        template = _read_hook(_TEMPLATE_DIR, hook_name)
        installed = _read_hook(_INSTALLED_DIR, hook_name)

        assert installed == template, (
            f"\nInstalled hook .atdd/hooks/{hook_name} differs from template.\n"
            f"Fix: Run `atdd init` or copy the template to sync.\n"
        )
