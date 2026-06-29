# URN: test:admit-substrate:substrate-cli-grouping:E002-SMOKE-001-grouped-add-list-parity
# Acceptance: acc:admit-substrate:E002-SMOKE-001-grouped-add-list-parity
# WMBT: wmbt:admit-substrate:E002
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""E002-SMOKE-001 (V1) — `atdd substrate add --path <pkg>` then `atdd substrate
list` behave identically to the flat verbs: add installs to the versioned home
with a digest-pinned lock; list renders the locked entry from the lockfile."""
from __future__ import annotations

import pathlib

VALID = pathlib.Path(__file__).parent / "fixtures" / "valid_extension"


def test_grouped_add_then_list_parity(tmp_path, run_atdd) -> None:
    proc = run_atdd(["substrate", "add", "--path", str(VALID)], tmp_path)
    assert proc.returncode == 0, proc.stdout + proc.stderr

    home = tmp_path / ".atdd" / "extensions" / "acme.extension.demo" / "0.1.0"
    assert home.is_dir()
    lock = tmp_path / ".atdd" / "substrate.lock.yaml"
    assert lock.exists() and "sha256:" in lock.read_text()

    proc2 = run_atdd(["substrate", "list"], tmp_path)
    assert proc2.returncode == 0, proc2.stdout + proc2.stderr
    assert "acme.extension.demo" in proc2.stdout
    assert "sha256:" in proc2.stdout
