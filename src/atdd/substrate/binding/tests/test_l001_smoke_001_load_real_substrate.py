# URN: test:bind-substrate-runtime:substrate-binding:L001-SMOKE-001-load-real-github
# Acceptance: acc:bind-substrate-runtime:L001-SMOKE-001-load-real-github
# WMBT: wmbt:bind-substrate-runtime:L001
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""L001-SMOKE-001 — loading a real admitted substrate (extension + python-pytest
provider, digest-pinned in a real substrate.lock.yaml) loads the enabled packages
from installed_path and indexes the implementations by realizes_convention,
importing no implementation code."""
from __future__ import annotations

from pathlib import Path

import pytest

from atdd.substrate.binding import composer, lock_loader
from atdd.substrate.binding.tests.conftest import install_extension, install_provider


@pytest.mark.smoke
def test_loads_real_substrate_and_indexes(tmp_path: Path) -> None:
    install_provider(tmp_path)
    install_extension(tmp_path, "acme.extension.demo", convention="demo.pr.gate")
    install_extension(tmp_path, "acme.extension.off", convention="demo.off", enabled=False)

    loaded = lock_loader.load_enabled_packages(tmp_path)
    ids = {p.id for p in loaded}
    assert "acme.extension.demo" in ids
    assert "atdd.workspace.python-pytest" in ids
    assert "acme.extension.off" not in ids  # disabled, not loaded

    index = composer.index_by_convention(loaded)
    assert index["demo.pr.gate"]["implementation_id"] == "acme.extension.demo.gate.impl"
    assert "demo.off" not in index
