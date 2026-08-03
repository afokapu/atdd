# URN: test:bind-substrate-runtime:substrate-binding:L001-UNIT-002-family-fans-out-to-conventions
# Acceptance: acc:bind-substrate-runtime:L001-UNIT-002-family-fans-out-to-conventions
# WMBT: wmbt:bind-substrate-runtime:L001
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""L001-UNIT-002 — one implementation may realize N conventions.

A FAMILY detector declares ``realizes_convention`` as a list and owns every
convention in it; the composer fans the single implementation out across all of
them. Ownership collisions are still refused, per convention.

``emits_rule_ids`` is CO-EMISSION, not ownership, and must never be indexed: a
detector may emit a rule_id another detector owns.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from atdd.substrate import installer
from atdd.substrate.binding import composer, lock_loader


def _install_family(
    project_root: Path,
    ext_id: str,
    *,
    realizes: str,
    emits: str = "",
) -> None:
    """Install an extension whose one implementation declares ``realizes``/``emits`` verbatim."""
    version = "0.1.0"
    dest = installer.install_path(project_root, "extension", ext_id, version)
    impl_dir = dest / "implementations" / "family"
    impl_dir.mkdir(parents=True, exist_ok=True)
    (dest / "atdd.extension.yaml").write_text(
        f"schema_version: '1.0.0'\nextension_id: {ext_id}\nkind: extension\nversion: '{version}'\n",
        encoding="utf-8",
    )
    (impl_dir / "atdd.implementation.yaml").write_text(
        "schema_version: '1.1.0'\n"
        "kind: implementation\n"
        f"implementation_id: {ext_id}.family.impl\n"
        "targets_workspace: atdd.workspace.python-pytest\n"
        "contract_version: '1.0.0'\n"
        f"realizes_convention: {realizes}\n"
        f"{emits}"
        "entrypoint: family.py\n",
        encoding="utf-8",
    )
    installer.upsert_lock_entry(
        project_root,
        {
            "id": ext_id,
            "kind": "extension",
            "version": version,
            "digest": installer.compute_digest(dest),
            "installed_path": str(dest.relative_to(project_root)),
            "enabled": True,
        },
    )


def test_list_valued_realizes_fans_one_impl_out_to_every_convention(tmp_path: Path) -> None:
    _install_family(tmp_path, "acme.extension.family", realizes="[conv.a, conv.b, conv.c]")

    index = composer.index_by_convention(lock_loader.load_enabled_packages(tmp_path))

    assert set(index) == {"conv.a", "conv.b", "conv.c"}
    for convention in ("conv.a", "conv.b", "conv.c"):
        assert index[convention]["implementation_id"] == "acme.extension.family.family.impl"


def test_scalar_realizes_still_indexes_one_convention(tmp_path: Path) -> None:
    _install_family(tmp_path, "acme.extension.single", realizes="conv.only")

    index = composer.index_by_convention(lock_loader.load_enabled_packages(tmp_path))

    assert set(index) == {"conv.only"}


def test_two_families_overlapping_on_one_convention_are_refused(tmp_path: Path) -> None:
    _install_family(tmp_path, "acme.extension.left", realizes="[conv.a, conv.shared]")
    _install_family(tmp_path, "acme.extension.right", realizes="[conv.shared, conv.z]")

    loaded = lock_loader.load_enabled_packages(tmp_path)

    with pytest.raises(composer.DuplicateConventionError, match="conv.shared"):
        composer.index_by_convention(loaded)


def test_emitted_but_unowned_rule_id_is_not_indexed(tmp_path: Path) -> None:
    """Co-emission must not create a binding — otherwise two detectors that both
    emit the same rule_id would collide even though only one owns it."""
    _install_family(
        tmp_path,
        "acme.extension.emitter",
        realizes="conv.owned",
        emits="emits_rule_ids: [conv.owned, conv.borrowed]\n",
    )

    index = composer.index_by_convention(lock_loader.load_enabled_packages(tmp_path))

    assert set(index) == {"conv.owned"}
    assert "conv.borrowed" not in index
