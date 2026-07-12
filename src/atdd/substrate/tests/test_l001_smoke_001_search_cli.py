# URN: test:admit-substrate:substrate-admission:L001-SMOKE-001-search-cli
# Acceptance: acc:admit-substrate:L001-SMOKE-001-search-cli
# WMBT: wmbt:admit-substrate:L001
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""L001-SMOKE-001 — `atdd search <query>` as a subprocess reads a configured
registry and prints the matching artifact, installing nothing."""
from __future__ import annotations

import pathlib
import textwrap

FIXTURE_REGISTRY = pathlib.Path(__file__).parent / "fixtures" / "registry"


def _write_substrate(tmp_path) -> None:
    atdd_dir = tmp_path / ".atdd"
    atdd_dir.mkdir(parents=True, exist_ok=True)
    (atdd_dir / "substrate.yaml").write_text(
        textwrap.dedent(
            f"""\
            schema_version: "1.0.0"
            registries:
              - id: test.local
                type: path
                source: "{FIXTURE_REGISTRY}"
                path: index.yaml
                trust: local
            """
        ),
        encoding="utf-8",
    )


def test_search_prints_match_and_installs_nothing(tmp_path, run_atdd) -> None:
    _write_substrate(tmp_path)
    proc = run_atdd(["search", "demo"], tmp_path)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "acme.extension.demo" in proc.stdout
    assert not (tmp_path / ".atdd" / "extensions").exists()
    assert not (tmp_path / ".atdd" / "workspaces").exists()
