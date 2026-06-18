# URN: test:admit-substrate:substrate-admission:C002-SMOKE-001-ambiguous-add-refused
# Acceptance: acc:admit-substrate:C002-SMOKE-001-ambiguous-add-refused
# WMBT: wmbt:admit-substrate:C002
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""C002-SMOKE-001 — `atdd add <ambiguous-alias>` as a subprocess exits non-zero,
prints the candidates, and installs nothing."""
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


def test_ambiguous_add_exits_nonzero_with_candidates(tmp_path, run_atdd) -> None:
    _write_substrate(tmp_path)
    proc = run_atdd(["add", "shared"], tmp_path)
    assert proc.returncode != 0
    out = proc.stdout + proc.stderr
    assert "acme.extension.alpha" in out and "acme.extension.beta" in out
    assert not (tmp_path / ".atdd" / "substrate.lock.yaml").exists()
