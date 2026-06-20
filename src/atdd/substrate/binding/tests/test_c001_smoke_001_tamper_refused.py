# URN: test:bind-substrate-runtime:substrate-binding:C001-SMOKE-001-tamper-refused-subprocess
# Acceptance: acc:bind-substrate-runtime:C001-SMOKE-001-tamper-refused-subprocess
# WMBT: wmbt:bind-substrate-runtime:C001
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""C001-SMOKE-001 — a real admitted package whose installed files are mutated after
admission is refused with a digest mismatch before any load/spawn; an intact
substrate loads cleanly."""
from __future__ import annotations

from pathlib import Path

import pytest

from atdd.substrate.binding import DigestMismatchError, lock_loader
from atdd.substrate.binding.tests.conftest import install_extension, install_provider


@pytest.mark.smoke
def test_real_tampered_substrate_is_refused(tmp_path: Path) -> None:
    install_provider(tmp_path)
    entry = install_extension(tmp_path, "acme.extension.demo", convention="demo.gate")

    # Intact substrate loads.
    assert lock_loader.load_enabled_packages(tmp_path)

    # Mutate the installed files AFTER the lock digest was recorded.
    tampered_file = tmp_path / entry["installed_path"] / "atdd.extension.yaml"
    tampered_file.write_text("schema_version: '9.9.9'\n", encoding="utf-8")

    # Now load refuses with a digest mismatch (the tamper boundary).
    with pytest.raises(DigestMismatchError):
        lock_loader.load_enabled_packages(tmp_path)
