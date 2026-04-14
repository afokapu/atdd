"""
Unit tests for `is_atdd_source_repo()` — the dogfood-scope guard.

Regression for #276: fixture-based dogfood tests must be gated by this helper
so they don't leak into consumer `atdd validate coder` runs. The helper must
return True only in the atdd source checkout and False in any pip-installed
/ vendored / consumer-repo layout.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from atdd.coach.utils.repo import is_atdd_source_repo, find_repo_root

pytestmark = [pytest.mark.platform]


def _make_fake_consumer_repo(root: Path) -> None:
    (root / ".git").mkdir(parents=True)
    (root / "pyproject.toml").write_text(
        '[project]\nname = "consumer-app"\nversion = "0.1.0"\n'
    )


def test_returns_false_when_pkg_in_site_packages(tmp_path, monkeypatch):
    """pip-installed atdd lives under .../site-packages/atdd — never source."""
    _make_fake_consumer_repo(tmp_path)
    fake_pkg = tmp_path / ".venv" / "lib" / "python3.14" / "site-packages" / "atdd"
    (fake_pkg).mkdir(parents=True)
    (fake_pkg / "__init__.py").write_text("")

    fake_atdd = type("FakeAtdd", (), {"__file__": str(fake_pkg / "__init__.py")})

    monkeypatch.chdir(tmp_path)
    find_repo_root.cache_clear()
    with patch.dict("sys.modules", {"atdd": fake_atdd}):
        assert is_atdd_source_repo() is False


def test_returns_false_when_pyproject_name_is_not_atdd(tmp_path, monkeypatch):
    """Consumer repo whose pyproject.toml has a different name — not source."""
    _make_fake_consumer_repo(tmp_path)
    consumer_pkg = tmp_path / "src" / "atdd"
    consumer_pkg.mkdir(parents=True)
    (consumer_pkg / "__init__.py").write_text("")

    fake_atdd = type("FakeAtdd", (), {"__file__": str(consumer_pkg / "__init__.py")})

    monkeypatch.chdir(tmp_path)
    find_repo_root.cache_clear()
    with patch.dict("sys.modules", {"atdd": fake_atdd}):
        assert is_atdd_source_repo() is False


def test_returns_true_inside_actual_source_repo():
    """When the real test is collected from the atdd source repo, True."""
    find_repo_root.cache_clear()
    assert is_atdd_source_repo() is True
