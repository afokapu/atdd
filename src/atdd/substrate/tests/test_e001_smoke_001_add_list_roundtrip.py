# URN: test:admit-substrate:substrate-admission:E001-SMOKE-001-add-list-roundtrip
# Acceptance: acc:admit-substrate:E001-SMOKE-001-add-list-roundtrip
# WMBT: wmbt:admit-substrate:E001
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""E001-SMOKE-001 — `atdd add --path <pkg>` then `atdd list --substrate` install to
the versioned home and render the locked entry with its digest; nothing under src/atdd."""
from __future__ import annotations

import pathlib

VALID = pathlib.Path(__file__).parent / "fixtures" / "valid_extension"


def test_add_then_list_substrate(tmp_path, run_atdd) -> None:
    proc = run_atdd(["add", "--path", str(VALID)], tmp_path)
    assert proc.returncode == 0, proc.stdout + proc.stderr

    home = tmp_path / ".atdd" / "extensions" / "acme.extension.demo" / "0.1.0"
    assert home.is_dir()
    lock = tmp_path / ".atdd" / "substrate.lock.yaml"
    assert lock.exists() and "sha256:" in lock.read_text()

    proc2 = run_atdd(["list", "--substrate"], tmp_path)
    assert proc2.returncode == 0, proc2.stdout + proc2.stderr
    assert "acme.extension.demo" in proc2.stdout
    assert "sha256:" in proc2.stdout
