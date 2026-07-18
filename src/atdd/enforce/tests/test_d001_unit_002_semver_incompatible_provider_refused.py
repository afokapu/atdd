# URN: test:govern-providers:D001-UNIT-002-semver-incompatible-provider-refused
# Acceptance: acc:govern-providers:D001-UNIT-002-semver-incompatible-provider-refused
# WMBT: wmbt:govern-providers:D001
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""GREEN Test for acc:govern-providers:D001-UNIT-002-semver-incompatible-provider-refused.

A provider whose installed contract version does not satisfy the requested caret
range is refused, and an absent workspace_id is refused — before any subprocess is
spawned. A drifted or missing mechanism never silently binds.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from atdd.enforce.resolution import (
    ContractRangeError,
    UnknownWorkspaceError,
    resolve_provider,
)

from .conftest import install_provider


def test_semver_incompatible_provider_refused(tmp_path: Path) -> None:
    install_provider(tmp_path, contract_version="1.1.0")
    roots = [tmp_path / ".atdd" / "workspaces"]

    # Incompatible major → refused on the contract range.
    with pytest.raises(ContractRangeError):
        resolve_provider(roots, "atdd.workspace.python-pytest", "^2.0.0")

    # A workspace_id absent from the roots → refused as unknown.
    with pytest.raises(UnknownWorkspaceError):
        resolve_provider(roots, "atdd.workspace.absent", "^1.0.0")

    # A compatible caret range against the same package resolves.
    resolved = resolve_provider(roots, "atdd.workspace.python-pytest", "^1.0.0")
    assert resolved.contract_version == "1.1.0"
