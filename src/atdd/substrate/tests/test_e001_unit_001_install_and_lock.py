# URN: test:admit-substrate:substrate-admission:E001-UNIT-001-install-and-lock
# Acceptance: acc:admit-substrate:E001-UNIT-001-install-and-lock
# WMBT: wmbt:admit-substrate:E001
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""E001-UNIT-001 — installing a validated package writes it to a versioned home,
records a stable sha256 digest + lock entry, lets `list` render the lock, and is
idempotent + digest-stable on re-install. Nothing is written under src/atdd."""
from __future__ import annotations

import pathlib

from atdd.substrate import admission, installer

VALID = pathlib.Path(__file__).parent / "fixtures" / "valid_extension"


def test_install_writes_versioned_home_and_lock_entry(tmp_path) -> None:
    res = admission.admit(VALID, project_root=tmp_path)

    home = tmp_path / ".atdd" / "extensions" / "acme.extension.demo" / "0.1.0"
    assert home.is_dir() and (home / "atdd.extension.yaml").exists()

    arts = installer.list_substrate(tmp_path)
    assert len(arts) == 1
    entry = arts[0]
    assert entry["id"] == "acme.extension.demo"
    assert entry["kind"] == "extension"
    assert entry["version"] == "0.1.0"
    assert entry["digest"].startswith("sha256:") and len(entry["digest"]) == len("sha256:") + 64
    assert entry["installed_path"] == ".atdd/extensions/acme.extension.demo/0.1.0"
    assert res.digest == entry["digest"]


def test_digest_stable_and_reinstall_idempotent(tmp_path) -> None:
    r1 = admission.admit(VALID, project_root=tmp_path)
    r2 = admission.admit(VALID, project_root=tmp_path)
    assert r1.digest == r2.digest
    assert len(installer.list_substrate(tmp_path)) == 1  # no duplicate lock entry


def test_compute_digest_is_deterministic() -> None:
    assert installer.compute_digest(VALID) == installer.compute_digest(VALID)


def test_list_reads_lock_only(tmp_path) -> None:
    admission.admit(VALID, project_root=tmp_path)
    # list_substrate reads the lockfile, not a filesystem scan
    assert [a["id"] for a in installer.list_substrate(tmp_path)] == ["acme.extension.demo"]
