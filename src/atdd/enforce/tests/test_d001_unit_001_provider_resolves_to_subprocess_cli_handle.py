# URN: test:govern-providers:D001-UNIT-001-provider-resolves-to-subprocess-cli-handle
# Acceptance: acc:govern-providers:D001-UNIT-001-provider-resolves-to-subprocess-cli-handle
# WMBT: wmbt:govern-providers:D001
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""GREEN Test for acc:govern-providers:D001-UNIT-001-provider-resolves-to-subprocess-cli-handle.

Resolving a workspace provider yields a filesystem path to its ``cli/scan.py``
subprocess entrypoint — a handle core shells out to, never an imported module.
The provider is the stack-specific MECHANISM; the boundary between core and that
mechanism is a CLI path (the V5 subprocess boundary), not a Python import.
"""
from __future__ import annotations

from pathlib import Path

from atdd.enforce.resolution import ResolvedProvider, resolve_provider

from .conftest import install_provider


def test_provider_resolves_to_subprocess_cli_handle(tmp_path: Path) -> None:
    install_provider(tmp_path, contract_version="1.1.0")
    roots = [tmp_path / ".atdd" / "workspaces"]

    resolved = resolve_provider(roots, "atdd.workspace.python-pytest", "^1.0.0")

    assert isinstance(resolved, ResolvedProvider)
    # The boundary is a filesystem path to a subprocess entrypoint, not a module/callable.
    assert isinstance(resolved.provider_cli_path, Path)
    assert resolved.provider_cli_path.is_file()
    assert resolved.provider_cli_path.name == "scan.py"
    assert not callable(resolved.provider_cli_path)
    assert resolved.contract_version == "1.1.0"
