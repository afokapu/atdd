# URN: test:bind-substrate-runtime:substrate-binding:C002-UNIT-001-contract-mismatch-refused
# Acceptance: acc:bind-substrate-runtime:C002-UNIT-001-contract-mismatch-refused
# WMBT: wmbt:bind-substrate-runtime:C002
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""C002-UNIT-001 — an implementation whose contract_version is SemVer-incompatible
with its targeted provider is refused; one whose targeted provider is absent from
the lock is refused; a compatible implementation binds."""
from __future__ import annotations

import pytest

from atdd.substrate.binding import (
    ContractMismatchError,
    ProviderNotFoundError,
    resolver,
)

# Providers as the lock presents them: id -> {contract_version, enabled}.
PROVIDERS = {
    "atdd.workspace.python-pytest": {"contract_version": "1.0.0", "enabled": True},
}


def _impl(impl_id: str, *, targets: str, contract: str) -> dict:
    return {
        "implementation_id": impl_id,
        "targets_workspace": targets,
        "contract_version": contract,
        "realizes_convention": "github.pr.merge-blocks-on-pre-smoke-close",
    }


def test_compatible_implementation_binds() -> None:
    binding = resolver.resolve_workspace(
        _impl("ok.impl", targets="atdd.workspace.python-pytest", contract="1.0.0"),
        PROVIDERS,
    )
    assert binding.workspace_id == "atdd.workspace.python-pytest"
    assert binding.implementation_id == "ok.impl"


def test_incompatible_major_is_refused() -> None:
    with pytest.raises(ContractMismatchError):
        resolver.resolve_workspace(
            _impl("drift.impl", targets="atdd.workspace.python-pytest", contract="2.0.0"),
            PROVIDERS,
        )


def test_absent_provider_is_refused() -> None:
    with pytest.raises(ProviderNotFoundError):
        resolver.resolve_workspace(
            _impl("orphan.impl", targets="atdd.workspace.node-vitest", contract="1.0.0"),
            PROVIDERS,
        )
