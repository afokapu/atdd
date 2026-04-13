"""
Unit tests for test_structured_logging module.

Covers the source-mode detection helper that distinguishes running inside the
atdd source repo (keep dogfooding scan of src/atdd/) from running in a
consumer repo with pip-installed atdd (skip dogfooding — atdd.__file__ lives
in site-packages and must not be scanned).

URN: urn:atdd:test:coder:structured_logging_unit
"""

from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path

import pytest


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


@pytest.fixture
def fake_consumer_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """
    Simulate a consumer repo layout with pip-installed atdd:

        tmp_path/
          python/app.py                              (1 bare logger call)
          .venv/lib/python3.X/site-packages/atdd/
             __init__.py                             (1 bare logger call — vendored)
    """
    consumer_python = tmp_path / "python" / "app.py"
    _write(
        consumer_python,
        "import logging\nlogger = logging.getLogger(__name__)\n"
        "def f():\n    logger.debug('consumer bare call')\n",
    )

    vendored_atdd_pkg = (
        tmp_path
        / ".venv"
        / "lib"
        / "python3.11"
        / "site-packages"
        / "atdd"
    )
    _write(vendored_atdd_pkg / "__init__.py", "")
    _write(
        vendored_atdd_pkg / "module.py",
        "import logging\nlogger = logging.getLogger(__name__)\n"
        "def g():\n    logger.debug('vendored bare call')\n",
    )

    # Marker so find_repo_root() returns tmp_path
    (tmp_path / ".git").mkdir()
    return tmp_path


def _reload_validator_with(
    monkeypatch: pytest.MonkeyPatch,
    repo_root: Path,
    atdd_file: Path,
):
    """
    Reload test_structured_logging with atdd.__file__ and find_repo_root()
    monkeypatched so module-level path constants pick up the fake layout.
    """
    import atdd
    from atdd.coach.utils import repo as repo_util

    monkeypatch.setattr(atdd, "__file__", str(atdd_file), raising=False)
    monkeypatch.setattr(repo_util, "find_repo_root", lambda *a, **k: repo_root)

    mod_name = "atdd.coder.validators.test_structured_logging"
    if mod_name in sys.modules:
        del sys.modules[mod_name]
    return importlib.import_module(mod_name)


def test_consumer_mode_skips_vendored_site_packages(
    fake_consumer_repo: Path, monkeypatch: pytest.MonkeyPatch
):
    """
    SPEC-CODER-LOG-0002-UNIT-01:
    When atdd is pip-installed (atdd.__file__ inside site-packages under
    .venv/), the dogfooding scan MUST be skipped. Only the consumer's
    python/ tree is scanned — yielding exactly 1 violation, not 2.
    """
    vendored_init = (
        fake_consumer_repo
        / ".venv"
        / "lib"
        / "python3.11"
        / "site-packages"
        / "atdd"
        / "__init__.py"
    )
    assert vendored_init.exists(), "fixture precondition"
    mod = _reload_validator_with(monkeypatch, fake_consumer_repo, vendored_init)

    assert mod.ATDD_PKG_DIR is None, (
        "ATDD_PKG_DIR must be None when atdd package lives outside REPO_ROOT "
        "(pip-installed in consumer repo)"
    )

    count, violations = mod.scan_structured_logging(fake_consumer_repo)
    assert count == 1, (
        f"Expected exactly 1 violation (consumer python/ only); "
        f"got {count}: {violations}"
    )
    assert any("python/app.py" in v for v in violations), violations
    assert not any("site-packages" in v for v in violations), (
        f"Vendored site-packages must not be scanned: {violations}"
    )


def test_source_mode_keeps_dogfooding_scan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """
    SPEC-CODER-LOG-0002-UNIT-02:
    When running inside the atdd source repo (atdd package dir is under
    REPO_ROOT, e.g. src/atdd/), the dogfooding scan MUST remain active so
    toolkit regressions in src/atdd/ are caught.
    """
    src_atdd_dir = tmp_path / "src" / "atdd"
    src_atdd_init = src_atdd_dir / "__init__.py"
    _write(src_atdd_init, "")
    _write(
        src_atdd_dir / "toolkit.py",
        "import logging\nlogger = logging.getLogger(__name__)\n"
        "def g():\n    logger.debug('toolkit bare call')\n",
    )
    consumer_python = tmp_path / "python" / "app.py"
    _write(
        consumer_python,
        "import logging\nlogger = logging.getLogger(__name__)\n"
        "def f():\n    logger.debug('consumer bare call')\n",
    )
    (tmp_path / ".git").mkdir()

    mod = _reload_validator_with(monkeypatch, tmp_path, src_atdd_init)

    assert mod.ATDD_PKG_DIR is not None, (
        "ATDD_PKG_DIR must be set when atdd package dir is under REPO_ROOT "
        "(source-mode dogfooding)"
    )

    count, violations = mod.scan_structured_logging(tmp_path)
    assert count == 2, f"Expected 2 violations (consumer + toolkit); got {count}: {violations}"
