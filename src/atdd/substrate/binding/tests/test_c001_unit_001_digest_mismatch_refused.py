# URN: test:bind-substrate-runtime:substrate-binding:C001-UNIT-001-digest-mismatch-refused
# Acceptance: acc:bind-substrate-runtime:C001-UNIT-001-digest-mismatch-refused
# WMBT: wmbt:bind-substrate-runtime:C001
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""C001-UNIT-001 — a package whose installed files were mutated after admission
(recomputed digest != lock digest) is refused before loading; an intact package
passes; the poisoned implementation never runs (sentinel file never written)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from atdd.substrate import installer
from atdd.substrate.binding import DigestMismatchError, lock_loader


def _install_extension(project_root: Path, ext_id: str, *, poison_sentinel: Path | None = None) -> dict:
    """Create an installed extension under .atdd/extensions/<id>/<version>/ and
    return a lock entry whose digest is taken NOW (matching the on-disk files)."""
    version = "0.1.0"
    dest = installer.install_path(project_root, "extension", ext_id, version)
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "atdd.extension.yaml").write_text(
        f"schema_version: '1.0.0'\nextension_id: {ext_id}\nkind: extension\nversion: '{version}'\n",
        encoding="utf-8",
    )
    impl_dir = dest / "implementations" / "poison"
    impl_dir.mkdir(parents=True, exist_ok=True)
    sentinel = poison_sentinel or (project_root / f"{ext_id}.SENTINEL")
    # A poisoned implementation module: writes a sentinel + raises if ever imported.
    (impl_dir / "poison.py").write_text(
        "from pathlib import Path\n"
        f"Path({str(sentinel)!r}).write_text('EXECUTED')\n"
        "raise RuntimeError('POISONED implementation executed')\n",
        encoding="utf-8",
    )
    digest = installer.compute_digest(dest)
    return {
        "id": ext_id,
        "kind": "extension",
        "version": version,
        "digest": digest,
        "installed_path": str(dest.relative_to(project_root)),
        "enabled": True,
    }


def test_intact_passes_and_tampered_is_refused(tmp_path: Path) -> None:
    project_root = tmp_path
    intact = _install_extension(project_root, "acme.extension.intact")
    tampered = _install_extension(project_root, "acme.extension.tampered")

    # Mutate the tampered package AFTER its lock digest was recorded.
    tampered_dir = project_root / tampered["installed_path"]
    (tampered_dir / "atdd.extension.yaml").write_text("schema_version: '9.9.9'\n", encoding="utf-8")
    sentinel = project_root / "acme.extension.tampered.SENTINEL"

    # The intact package verifies cleanly.
    lock_loader.verify_package_digest(project_root, intact)

    # The tampered package is refused with a digest mismatch, before any load.
    with pytest.raises(DigestMismatchError):
        lock_loader.verify_package_digest(project_root, tampered)

    # The poisoned implementation never ran and was never imported.
    assert not sentinel.exists()
    assert not any(m.endswith("poison") for m in list(sys.modules))
