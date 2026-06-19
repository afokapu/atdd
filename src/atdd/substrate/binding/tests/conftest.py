"""Binding-test collection config + shared real-substrate builders.

The ``fixtures/`` tree holds real implementation tests that are executed only by
the provider via PROVIDER-SPAWN (a subprocess pytest), never by the main suite —
collecting them here would both duplicate basenames and intentionally error
(``crashing_impl`` raises at import on purpose). Exclude the whole fixtures tree.
"""
from __future__ import annotations

from pathlib import Path

import pytest

collect_ignore_glob = ["fixtures/*"]


def install_extension(
    project_root: Path, ext_id: str, *, convention: str, enabled: bool = True
) -> dict:
    """Install a real extension (manifest + implementation manifest) under the
    versioned home and append a digest-pinned lock entry. Returns the entry."""
    from atdd.substrate import installer

    version = "0.1.0"
    dest = installer.install_path(project_root, "extension", ext_id, version)
    impl_dir = dest / "implementations" / "gate"
    impl_dir.mkdir(parents=True, exist_ok=True)
    (dest / "atdd.extension.yaml").write_text(
        f"schema_version: '1.0.0'\nextension_id: {ext_id}\nkind: extension\nversion: '{version}'\n",
        encoding="utf-8",
    )
    (impl_dir / "atdd.implementation.yaml").write_text(
        "schema_version: '1.0.0'\nkind: implementation\n"
        f"implementation_id: {ext_id}.gate.impl\n"
        "targets_workspace: atdd.workspace.python-pytest\n"
        "contract_version: '1.0.0'\n"
        f"realizes_convention: {convention}\nentrypoint: gate.py\n",
        encoding="utf-8",
    )
    return installer.upsert_lock_entry(
        project_root,
        {
            "id": ext_id, "kind": "extension", "version": version,
            "digest": installer.compute_digest(dest),
            "installed_path": str(dest.relative_to(project_root)),
            "enabled": enabled,
        },
    )["artifacts"][-1]


def install_provider(project_root: Path, ws_id: str = "atdd.workspace.python-pytest") -> dict:
    """Install a real workspace provider (declares contract_version) + lock entry."""
    from atdd.substrate import installer

    version = "0.1.0"
    dest = installer.install_path(project_root, "workspace", ws_id, version)
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "atdd.workspace.yaml").write_text(
        f"schema_version: '1.0.0'\nworkspace_id: {ws_id}\nkind: workspace\n"
        f"version: '{version}'\ncontract_version: '1.0.0'\n",
        encoding="utf-8",
    )
    return installer.upsert_lock_entry(
        project_root,
        {
            "id": ws_id, "kind": "workspace", "version": version,
            "digest": installer.compute_digest(dest),
            "installed_path": str(dest.relative_to(project_root)),
            "enabled": True,
        },
    )["artifacts"][-1]


@pytest.fixture
def substrate_builders():
    """Expose the real-substrate builders to smoke tests."""
    return install_extension, install_provider
