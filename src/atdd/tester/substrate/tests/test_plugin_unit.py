# URN: component:govern-lifecycle:enforcement-substrate:harness-plugin-unit:backend:tests
# Runtime: python
# Purpose: Unit-level coverage of substrate plugin helpers — header parsing, test-root resolution, binding dispatch (issue #411).

"""Unit tests for ``atdd.tester.substrate.plugin``.

These tests exercise the plugin's pure helpers — test-root resolution
order, header parsing, and the ``bind_for_acceptance`` dispatch — without
spinning up a pytest session. The integration tests (pytester-based)
cover the full hook flow and acceptance criteria 1-7 from issue #411.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from atdd.coach.utils.rule_binding import RuleNotInRegistryError
from atdd.tester.substrate import plugin as plug


# ---------------------------------------------------------------------------
# _resolve_test_roots — order: .atdd/config.yaml > pyproject testpaths > tests/
# ---------------------------------------------------------------------------

def _make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "tests").mkdir()
    return repo


def test_resolve_test_roots_prefers_atdd_config(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    custom = repo / "specs"
    custom.mkdir()
    (repo / ".atdd").mkdir()
    (repo / ".atdd" / "config.yaml").write_text(
        "repo:\n  test_root: specs\n", encoding="utf-8",
    )
    (repo / "pyproject.toml").write_text(
        '[tool.pytest.ini_options]\ntestpaths = ["tests"]\n', encoding="utf-8",
    )

    roots = plug._resolve_test_roots(repo)

    assert roots == [custom.resolve()]


def test_resolve_test_roots_falls_back_to_pyproject(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    pkg_tests = repo / "pkg_tests"
    pkg_tests.mkdir()
    (repo / "pyproject.toml").write_text(
        '[tool.pytest.ini_options]\ntestpaths = ["pkg_tests"]\n',
        encoding="utf-8",
    )

    roots = plug._resolve_test_roots(repo)

    assert roots == [pkg_tests.resolve()]


def test_resolve_test_roots_defaults_to_tests(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)

    roots = plug._resolve_test_roots(repo)

    assert roots == [(repo / "tests").resolve()]


def test_resolve_test_roots_drops_missing_directories(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    (repo / "pyproject.toml").write_text(
        '[tool.pytest.ini_options]\ntestpaths = ["does-not-exist"]\n',
        encoding="utf-8",
    )

    roots = plug._resolve_test_roots(repo)

    assert roots == []


# ---------------------------------------------------------------------------
# _parse_acceptance_header — uses TestResolver semantics
# ---------------------------------------------------------------------------

_ANCHORED_TEST = '''\
# URN: test:foo:D003-acc-unit-001
# Acceptance: acc:foo:D003-UNIT-001-thing
# WMBT: wmbt:foo:D003
# Phase: GREEN
# Layer: domain

def test_thing():
    assert False
'''

_UNANCHORED_TEST = '''\
def test_anything():
    assert True
'''


def test_parse_acceptance_header_returns_urn(tmp_path: Path) -> None:
    f = tmp_path / "test_foo.py"
    f.write_text(_ANCHORED_TEST, encoding="utf-8")

    assert plug._parse_acceptance_header(f) == "acc:foo:D003-UNIT-001-thing"


def test_parse_acceptance_header_returns_none_for_plain_test(tmp_path: Path) -> None:
    f = tmp_path / "test_bar.py"
    f.write_text(_UNANCHORED_TEST, encoding="utf-8")

    assert plug._parse_acceptance_header(f) is None


def test_parse_acceptance_header_returns_none_for_missing_file(tmp_path: Path) -> None:
    f = tmp_path / "nonexistent.py"

    assert plug._parse_acceptance_header(f) is None


# ---------------------------------------------------------------------------
# _bind_for_acceptance — derive + bind_rule, swallow RuleNotInRegistryError
# ---------------------------------------------------------------------------

def test_bind_for_acceptance_returns_metadata_when_rule_exists() -> None:
    fake_meta = object()
    with patch.object(plug, "bind_rule", return_value=fake_meta) as bind_mock:
        result = plug._bind_for_acceptance("acc:foo:D003-UNIT-001-thing")

    assert result is fake_meta
    bind_mock.assert_called_once_with("repo.foo.D003-acc-unit-001")


def test_bind_for_acceptance_returns_none_when_walker_rejected_acceptance() -> None:
    with patch.object(
        plug, "bind_rule", side_effect=RuleNotInRegistryError("nope"),
    ):
        result = plug._bind_for_acceptance("acc:foo:D003-UNIT-001-thing")

    assert result is None


def test_bind_for_acceptance_returns_none_for_malformed_urn() -> None:
    # Trailing junk so derive_repo_rule_id raises RepoYamlValidationError.
    assert plug._bind_for_acceptance("not-an-acc-urn") is None


# ---------------------------------------------------------------------------
# _validator_id_for_item / _format_detail / _severity_or_default
# ---------------------------------------------------------------------------

class _FakeItem:
    def __init__(self, *, name: str, path: Path, cls: Any = None) -> None:
        self.name = name
        self.path = path
        self.cls = cls


def test_validator_id_uses_module_basename(tmp_path: Path) -> None:
    item = _FakeItem(name="test_thing", path=tmp_path / "test_foo.py")

    assert plug._validator_id_for_item(item) == "test_foo::test_thing"


def test_validator_id_includes_class_for_class_based_tests(tmp_path: Path) -> None:
    class _Cls:
        pass

    item = _FakeItem(name="test_thing", path=tmp_path / "test_foo.py", cls=_Cls)

    assert plug._validator_id_for_item(item) == "test_foo::_Cls::test_thing"


def test_format_detail_collapses_to_first_line() -> None:
    class _ExcInfo:
        value = AssertionError("failed bad\nsecond line\nthird")

    detail = plug._format_detail(_ExcInfo())

    assert detail == "failed bad"


def test_format_detail_falls_back_to_assertion_error() -> None:
    class _ExcInfo:
        value = AssertionError()

    assert plug._format_detail(_ExcInfo()) == "AssertionError"


def test_severity_or_default_returns_constant_four_for_non_int() -> None:
    class _Rule:
        severity = "error"

    assert plug._severity_or_default(_Rule()) == 4


def test_severity_or_default_returns_existing_int() -> None:
    class _Rule:
        severity = 5

    assert plug._severity_or_default(_Rule()) == 5
