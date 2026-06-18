# URN: test:admit-substrate:substrate-admission:C001-UNIT-001-no-runtime-execution
# Acceptance: acc:admit-substrate:C001-UNIT-001-no-runtime-execution
# WMBT: wmbt:admit-substrate:C001
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""C001-UNIT-001 — admitting a package whose implementation raises on import (and
records a sentinel) completes the validate+compose path without ever importing or
running that module: no poisoned RuntimeError, no sentinel, executed_implementations == []."""
from __future__ import annotations

import pathlib
import sys

import pytest

from atdd.substrate import admission

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "poisoned_extension"


def _poison_modules() -> list[str]:
    return [name for name in sys.modules if "poison" in name.lower()]


def test_validate_and_compose_never_executes_implementation(tmp_path, monkeypatch) -> None:
    sentinel = tmp_path / "executed.sentinel"
    monkeypatch.setenv("ATDD_C001_SENTINEL", str(sentinel))
    before = set(_poison_modules())

    # The validate+compose path runs over a manifest-valid package whose
    # implementation is poisoned. It must complete without touching that module.
    result = admission.validate_and_compose(FIXTURE)

    assert result.executed_implementations == []
    assert not sentinel.exists(), "poisoned implementation was executed during admission"
    assert set(_poison_modules()) == before, "poisoned implementation module was imported"


def test_poisoned_module_raises_if_actually_imported(monkeypatch, tmp_path) -> None:
    # Guard: prove the fixture is genuinely poisoned, so the test above is meaningful.
    sentinel = tmp_path / "guard.sentinel"
    monkeypatch.setenv("ATDD_C001_SENTINEL", str(sentinel))
    monkeypatch.syspath_prepend(str(FIXTURE / "implementations" / "poison"))
    with pytest.raises(RuntimeError, match="POISONED"):
        import poison  # noqa: F401
    sys.modules.pop("poison", None)
