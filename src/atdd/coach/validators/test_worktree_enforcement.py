"""
E012: Worktree enforcement — hook template regression tests.

Validates that hook templates enforce branch-scoped protection for main/master
without path-prefix escape hatches. These are deterministic, offline tests that
read template file content and assert structural properties.

Run: PYTHONPATH=src python3 -m pytest -q src/atdd/coach/validators/test_worktree_enforcement.py -v
"""
# Acceptance: acc:govern-lifecycle:D019-UNIT-001-prepush-template-runs-validate-coder
# Acceptance: acc:govern-lifecycle:D019-UNIT-002-prepush-template-runs-validate-coach
# Acceptance: acc:govern-lifecycle:D019-UNIT-003-prepush-skip-env-var
# Acceptance: acc:govern-lifecycle:D019-UNIT-004-prepush-skipped-in-ci
# Acceptance: acc:govern-lifecycle:D019-UNIT-005-prepush-chains-existing-git-hook
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


# URN: test:govern-lifecycle:blocking-prepush-validator-hook:D019-UNIT-001-prepush-template-runs-validate-coder
# URN: test:govern-lifecycle:blocking-prepush-validator-hook:D019-UNIT-002-prepush-template-runs-validate-coach
# URN: test:govern-lifecycle:blocking-prepush-validator-hook:D019-UNIT-003-prepush-skip-env-var
# URN: test:govern-lifecycle:blocking-prepush-validator-hook:D019-UNIT-004-prepush-skipped-in-ci
# URN: test:govern-lifecycle:blocking-prepush-validator-hook:D019-UNIT-005-prepush-chains-existing-git-hook
class TestPrePushBlockingValidators:
    """D019: pre-push hook runs atdd validate coder and atdd validate coach as blocking checks."""

    def test_pre_push_template_runs_validate_coder(self):
        """
        acc:govern-lifecycle:D019-UNIT-001: Template invokes atdd validate coder.

        Given: src/atdd/coach/templates/hooks/pre-push
        When: File content is read
        Then: 'atdd validate coder' appears in the template
        """
        content = _read_hook(_TEMPLATE_DIR, "pre-push")

        assert "atdd validate coder" in content, (
            "\npre-push template missing 'atdd validate coder'.\n"
            "Fix: Add blocking 'atdd validate coder || exit 1' to the pre-push template.\n"
        )

    def test_pre_push_template_runs_validate_coach(self):
        """
        acc:govern-lifecycle:D019-UNIT-002: Template invokes atdd validate coach.

        Given: src/atdd/coach/templates/hooks/pre-push
        When: File content is read
        Then: 'atdd validate coach' appears in the template
        """
        content = _read_hook(_TEMPLATE_DIR, "pre-push")

        assert "atdd validate coach" in content, (
            "\npre-push template missing 'atdd validate coach'.\n"
            "Fix: Add blocking 'atdd validate coach || exit 1' to the pre-push template.\n"
        )

    def test_pre_push_template_validator_blocks_on_failure(self):
        """
        acc:govern-lifecycle:D019-UNIT-001/002: Validators exit non-zero on failure.

        Given: src/atdd/coach/templates/hooks/pre-push
        When: File content is read
        Then: The validator calls use a blocking pattern (|| exit 1 or set -e context)
        """
        content = _read_hook(_TEMPLATE_DIR, "pre-push")

        # Both validators must be present; the exit-1 pattern enforces blocking
        assert "atdd validate coder" in content
        assert "atdd validate coach" in content

        # At least one explicit exit 1 after validator calls (may use set -e or explicit ||)
        # Collect all occurrences of 'exit 1'
        exit_ones = [m.start() for m in re.finditer(r"exit 1", content)]
        validate_coder_pos = content.find("atdd validate coder")
        validate_coach_pos = content.find("atdd validate coach")

        # There must be exit-1 calls that appear after or adjacent to the validators
        post_validator_exits = [pos for pos in exit_ones if pos > min(validate_coder_pos, validate_coach_pos)]
        assert len(post_validator_exits) >= 1, (
            "\npre-push template has no 'exit 1' after the validator calls.\n"
            "Fix: Use '|| exit 1' after each validator or keep the validators under 'set -e'.\n"
        )

    def test_pre_push_template_has_skip_env_var(self):
        """
        acc:govern-lifecycle:D019-UNIT-003: Template checks ATDD_SKIP_PREPUSH_VALIDATE.

        Given: src/atdd/coach/templates/hooks/pre-push
        When: File content is read
        Then: ATDD_SKIP_PREPUSH_VALIDATE appears in the template
        """
        content = _read_hook(_TEMPLATE_DIR, "pre-push")

        assert "ATDD_SKIP_PREPUSH_VALIDATE" in content, (
            "\npre-push template missing ATDD_SKIP_PREPUSH_VALIDATE override.\n"
            "Fix: Add 'if [ \"${ATDD_SKIP_PREPUSH_VALIDATE:-0}\" = \"1\" ]; then' guard.\n"
        )

    def test_pre_push_template_validator_section_skipped_in_ci(self):
        """
        acc:govern-lifecycle:D019-UNIT-004: Validator section is CI-aware.

        Given: src/atdd/coach/templates/hooks/pre-push
        When: File content is read
        Then: The validator section checks CI= so it is skipped in CI environments
        """
        content = _read_hook(_TEMPLATE_DIR, "pre-push")

        # The template must guard the validator section with a CI check
        # (separate from the existing version-gate CI bypass)
        validate_coder_pos = content.find("atdd validate coder")
        assert validate_coder_pos > 0

        # Find any CI check that precedes the validator calls
        ci_checks = [m.start() for m in re.finditer(r'CI[^_]', content)]
        pre_validator_ci = [pos for pos in ci_checks if pos < validate_coder_pos]
        assert len(pre_validator_ci) >= 1, (
            "\npre-push template validator section has no CI guard before 'atdd validate coder'.\n"
            "Fix: Wrap the validator calls in 'if [ \"${CI:-}\" != \"true\" ]; then ... fi'.\n"
        )

    def test_pre_push_template_chains_existing_git_hook(self):
        """
        acc:govern-lifecycle:D019-UNIT-005: Template chains .git/hooks/pre-push if present.

        Given: src/atdd/coach/templates/hooks/pre-push
        When: File content is read
        Then: The template contains logic to call the original .git/hooks/pre-push when executable
        """
        content = _read_hook(_TEMPLATE_DIR, "pre-push")

        # Template must reference the git-common-dir hooks path to chain existing hook
        has_chain_logic = (
            "git-common-dir" in content
            or "git rev-parse --git-common-dir" in content
            or ("hooks/pre-push" in content and "git rev-parse" in content)
        )
        assert has_chain_logic, (
            "\npre-push template has no chaining logic for existing .git/hooks/pre-push.\n"
            "Fix: Add detection of ${git-common-dir}/hooks/pre-push and call it if executable.\n"
        )
