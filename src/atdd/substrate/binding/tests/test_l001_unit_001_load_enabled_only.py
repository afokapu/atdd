# URN: test:bind-substrate-runtime:substrate-binding:L001-UNIT-001-load-enabled-only
# Acceptance: acc:bind-substrate-runtime:L001-UNIT-001-load-enabled-only
# WMBT: wmbt:bind-substrate-runtime:L001
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""L001-UNIT-001 — loading a lock with one enabled and one disabled extension
loads only the enabled package and indexes its implementations by
realizes_convention; an on-disk package absent from the lock is ignored."""
from __future__ import annotations

from pathlib import Path

from atdd.substrate import installer
from atdd.substrate.binding import composer, lock_loader


def _install_extension(
    project_root: Path, ext_id: str, *, convention: str, enabled: bool, in_lock: bool
) -> None:
    version = "0.1.0"
    dest = installer.install_path(project_root, "extension", ext_id, version)
    impl_dir = dest / "implementations" / "gate"
    impl_dir.mkdir(parents=True, exist_ok=True)
    (dest / "atdd.extension.yaml").write_text(
        f"schema_version: '1.0.0'\nextension_id: {ext_id}\nkind: extension\nversion: '{version}'\n",
        encoding="utf-8",
    )
    (impl_dir / "atdd.implementation.yaml").write_text(
        "schema_version: '1.0.0'\n"
        "kind: implementation\n"
        f"implementation_id: {ext_id}.gate.impl\n"
        "targets_workspace: atdd.workspace.python-pytest\n"
        "contract_version: '1.0.0'\n"
        f"realizes_convention: {convention}\n"
        "entrypoint: gate.py\n",
        encoding="utf-8",
    )
    if in_lock:
        installer.upsert_lock_entry(
            project_root,
            {
                "id": ext_id,
                "kind": "extension",
                "version": version,
                "digest": installer.compute_digest(dest),
                "installed_path": str(dest.relative_to(project_root)),
                "enabled": enabled,
            },
        )


def test_loads_enabled_only_and_indexes_by_convention(tmp_path: Path) -> None:
    project_root = tmp_path
    _install_extension(project_root, "acme.extension.on", convention="conv.on", enabled=True, in_lock=True)
    _install_extension(project_root, "acme.extension.off", convention="conv.off", enabled=False, in_lock=True)
    _install_extension(project_root, "acme.extension.ghost", convention="conv.ghost", enabled=True, in_lock=False)

    loaded = lock_loader.load_enabled_packages(project_root)
    loaded_ids = {p.id for p in loaded}

    assert loaded_ids == {"acme.extension.on"}

    index = composer.index_by_convention(loaded)
    assert set(index) == {"conv.on"}
    assert index["conv.on"]["implementation_id"] == "acme.extension.on.gate.impl"
    assert index["conv.on"]["_package_id"] == "acme.extension.on"
    # The disabled and lock-absent packages contributed nothing.
    assert "conv.off" not in index
    assert "conv.ghost" not in index
