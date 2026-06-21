# URN: test:bind-substrate-runtime:substrate-binding:E001-SMOKE-001-real-pytest-spawn
# Acceptance: acc:bind-substrate-runtime:E001-SMOKE-001-real-pytest-spawn
# WMBT: wmbt:bind-substrate-runtime:E001
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""E001-SMOKE-001 — the REAL python-pytest provider adapter provider-spawns a real
implementation as a pytest subprocess and its Violation is captured over the
violation-output contract; core imports neither the provider nor the impl.

Real infra: the shipped fixture provider adapter is the python-pytest provider's
own self-contained ``adapter/run.py``; the implementations are real pytest tests
run in a real subprocess (no mocks)."""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

_FIX = Path(__file__).parent / "fixtures"
_ADAPTER = _FIX / "provider" / "adapter"


def _materialize(src: Path, tmp_path: Path) -> Path:
    """Copy an impl test dir OUTSIDE the repo tree, mirroring a materialized
    workspace instance so the core repo's pytest config does not apply."""
    dest = tmp_path / src.name
    shutil.copytree(src, dest)
    return dest


@pytest.mark.smoke
def test_real_provider_spawn_captures_violation(tmp_path: Path) -> None:
    from atdd.substrate.binding import binder

    result = binder.provider_spawn(
        adapter_dir=_ADAPTER,
        implementation_id="github.pr.merge-blocks-on-pre-smoke-close.impl",
        test_path=_materialize(_FIX / "failing_impl", tmp_path),
    )

    # The real pytest subprocess ran and reported exactly one violation, keyed to
    # the implementation id, over the provider's violation-output contract.
    assert result.ran is True
    assert result.exit_code == 1
    assert len(result.violations) == 1
    assert result.violations[0]["rule_id"] == "github.pr.merge-blocks-on-pre-smoke-close.impl"

    # Core imported neither the provider adapter nor the implementation.
    assert getattr(sys.modules.get("run"), "__file__", "") != str(_ADAPTER / "run.py")


@pytest.mark.smoke
def test_real_provider_spawn_passing_impl_has_no_violations(tmp_path: Path) -> None:
    from atdd.substrate.binding import binder

    result = binder.provider_spawn(
        adapter_dir=_ADAPTER,
        implementation_id="clean.impl",
        test_path=_materialize(_FIX / "passing_impl", tmp_path),
    )
    assert result.ran is True
    assert result.exit_code == 0
    assert result.violations == []
