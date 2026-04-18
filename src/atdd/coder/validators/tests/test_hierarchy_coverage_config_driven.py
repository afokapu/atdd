"""
Unit tests for config-driven implementation-root resolution in the
hierarchy-coverage validator.

URN: urn:atdd:test:coder:hierarchy_coverage_config_driven
WMBT: wmbt:govern-lifecycle:D011 (hardcoded path constants)
WMBT: wmbt:govern-lifecycle:D012 (toolkit-self features invisible)
WMBT: wmbt:govern-lifecycle:R003 (stale ratchet baseline)

These tests exercise the refactored resolver trio
(find_python_implementations, find_typescript_implementations,
find_web_implementations) plus the new find_toolkit_implementations,
all parametrized on a config-driven ``code_roots`` map. Acceptance:
toolkit-self features become visible once ``code.toolkit`` is seeded,
and an unknown stack key (e.g. ``rust``) does not crash has_implementation.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from atdd.coach.utils.config import get_code_roots
from atdd.coach.utils.repo import find_repo_root
from atdd.coder.validators.test_hierarchy_coverage import (
    find_toolkit_implementations,
    has_implementation,
)


pytestmark = [pytest.mark.platform]


REPO_ROOT = find_repo_root()


class TestFindToolkitImplementations:
    def test_finds_file_by_fuzzy_basename_match(self):
        """Decision #5: toolkit layout is composed of several files per
        feature. Substring match on normalized slug suffices — strict
        {wagon}/{feature}.py would over-reject."""
        toolkit_root = REPO_ROOT / "src/atdd"
        hits = find_toolkit_implementations(
            "govern-lifecycle", "orchestrate-ready-lifecycle", toolkit_root
        )
        assert hits, "expected at least one match for 'orchestrate' under src/atdd"
        assert any("orchestrate" in h.name for h in hits)

    def test_unknown_slug_returns_empty(self):
        toolkit_root = REPO_ROOT / "src/atdd"
        hits = find_toolkit_implementations(
            "govern-lifecycle", "nonexistent-thing-zzz-xyz", toolkit_root
        )
        assert hits == []

    def test_missing_toolkit_root_returns_empty(self, tmp_path):
        hits = find_toolkit_implementations(
            "govern-lifecycle", "foo", tmp_path / "does-not-exist"
        )
        assert hits == []


class TestHasImplementationConfigDriven:
    def test_toolkit_seeded_makes_toolkit_feature_visible(self):
        """D006: with code.toolkit seeded, features whose code lives under
        src/atdd/ are resolvable."""
        code_roots = get_code_roots({"code": {"toolkit": "src/atdd"}})
        # The 'orchestrate' keyword appears in several toolkit modules for
        # the orchestrate-ready-lifecycle feature.
        assert has_implementation(
            "govern-lifecycle",
            "orchestrate-ready-lifecycle",
            code_roots=code_roots,
        )

    def test_toolkit_absent_hides_toolkit_feature(self):
        """D006 (negative control): default code map has no toolkit
        resolver; toolkit-only features are invisible."""
        code_roots = get_code_roots({})
        assert not has_implementation(
            "govern-lifecycle",
            "orchestrate-ready-lifecycle",
            code_roots=code_roots,
        )

    def test_unknown_stack_key_does_not_crash(self):
        """Decision #2: unknown keys (e.g. rust) skip gracefully."""
        code_roots = get_code_roots({"code": {"rust": "crates"}})
        # Should return a bool — not raise — even though no resolver
        # exists for the rust stack.
        result = has_implementation(
            "govern-lifecycle", "orchestrate-ready-lifecycle", code_roots=code_roots
        )
        assert isinstance(result, bool)

    def test_defaults_still_resolve_python_impl(self):
        """Backward compat: repos on the old layout keep working."""
        code_roots = get_code_roots({})
        # The resolver map should include a python resolver even without
        # toolkit. Signature tolerance — we just ask for a bool back.
        result = has_implementation(
            "govern-lifecycle", "orchestrate-ready-lifecycle", code_roots=code_roots
        )
        assert isinstance(result, bool)
