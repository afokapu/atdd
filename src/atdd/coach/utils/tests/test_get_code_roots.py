"""
Unit tests for atdd.coach.utils.config.get_code_roots().

URN: urn:atdd:test:coach:utils:get_code_roots
WMBT: wmbt:govern-lifecycle:D011 (hardcoded implementation-root constants)
WMBT: wmbt:govern-lifecycle:D013 (config schema drift)

The helper is the single source of truth for resolving the `code:` block
in `.atdd/config.yaml` to a map of stack-name → Path. Defaults cover the
python/supabase/web triad; the toolkit root is opt-in per Decision #1.
Unknown stack keys are preserved so forward-compatible consumers can
declare future stacks before resolvers exist (Decision #2).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from atdd.coach.utils.config import get_code_roots


pytestmark = [pytest.mark.platform]


class TestDefaults:
    def test_empty_config_returns_python_supabase_web_only(self):
        roots = get_code_roots({})
        assert set(roots) == {"python", "supabase", "web"}

    def test_toolkit_not_in_defaults(self):
        """Decision #1: toolkit root is opt-in to avoid consumer repos
        accidentally indexing a vendored src/atdd copy as their own impl."""
        roots = get_code_roots({})
        assert "toolkit" not in roots

    def test_default_values_are_path_objects(self):
        roots = get_code_roots({})
        for value in roots.values():
            assert isinstance(value, Path)

    def test_default_paths_match_existing_layout(self):
        roots = get_code_roots({})
        assert roots["python"] == Path("python")
        assert roots["supabase"] == Path("supabase/functions")
        assert roots["web"] == Path("web/src")


class TestMerge:
    def test_toolkit_override_adds_to_defaults(self):
        roots = get_code_roots({"code": {"toolkit": "src/atdd"}})
        assert set(roots) >= {"python", "supabase", "web", "toolkit"}
        assert roots["toolkit"] == Path("src/atdd")

    def test_override_replaces_default_value(self):
        roots = get_code_roots({"code": {"python": "backend"}})
        assert roots["python"] == Path("backend")
        # Other defaults remain untouched
        assert roots["supabase"] == Path("supabase/functions")
        assert roots["web"] == Path("web/src")

    def test_unknown_stack_key_is_preserved(self):
        """Decision #2: config may declare future stacks (rust, go, dart)
        before resolvers ship. get_code_roots preserves them verbatim —
        the validator is responsible for skipping unknown keys."""
        roots = get_code_roots({"code": {"rust": "crates"}})
        assert "rust" in roots
        assert roots["rust"] == Path("crates")


class TestInputSafety:
    def test_none_config_returns_defaults(self):
        roots = get_code_roots(None)
        assert set(roots) == {"python", "supabase", "web"}

    def test_missing_code_key_returns_defaults(self):
        roots = get_code_roots({"version": "1.0"})
        assert set(roots) == {"python", "supabase", "web"}

    def test_empty_code_dict_returns_defaults(self):
        roots = get_code_roots({"code": {}})
        assert set(roots) == {"python", "supabase", "web"}

    def test_non_dict_code_falls_back_to_defaults(self):
        """A malformed config (e.g. code: [] from a copy-paste error) must
        not crash the validator — fall back to defaults."""
        roots = get_code_roots({"code": []})
        assert set(roots) == {"python", "supabase", "web"}
