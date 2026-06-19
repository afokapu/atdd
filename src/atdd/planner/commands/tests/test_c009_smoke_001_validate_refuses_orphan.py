# URN: test:author-atdd-substrate:package-composition:C009-SMOKE-001-validate-refuses-orphan
# Acceptance: acc:author-atdd-substrate:C009-SMOKE-001-validate-refuses-orphan
# WMBT: wmbt:author-atdd-substrate:C009
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""C009-SMOKE-001 — `atdd validate package` refuses an extension whose owned
convention node is referenced by no relationship edge, and passes when every
owned node is wired into the extension's local graph."""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
import yaml

from atdd.planner.commands import compose


def _node(d: Path, rid: str) -> str:
    f = d / f"{rid}.convention.yaml"
    f.write_text(
        f"schema_version: 1.1.0\nrule_id: {rid}\nkind: rule\nstatus: active\n"
        f"statement: stub rule for the orphan smoke.\nterms:\n  - term_id: t\n    text: t\n",
        encoding="utf-8",
    )
    return f.name


def _build_extension(root: Path, edges: list[dict]) -> Path:
    ext = root / "acme.extension.probe"
    ext.mkdir(parents=True)
    convs = [_node(ext, "acme.probe.alpha"), _node(ext, "acme.probe.beta")]
    (ext / "atdd.extension.yaml").write_text(
        textwrap.dedent(
            f"""\
            schema_version: "1.0.0"
            extension_id: acme.extension.probe
            version: "0.1.0"
            kind: extension
            role: coder
            flow_wagon: validate-source-surface
            feature: probe
            owns:
              conventions: [{convs[0]}, {convs[1]}]
            """
        ),
        encoding="utf-8",
    )
    (ext / "relationships.yaml").write_text(
        yaml.safe_dump({"schema_version": "1.0.0", "graph_id": "acme.probe", "edges": edges}),
        encoding="utf-8",
    )
    return ext


def test_validate_package_refuses_orphan_node(tmp_path) -> None:
    # alpha is wired to itself; beta is referenced by no edge → orphan
    ext = _build_extension(tmp_path, [{"from": "acme.probe.alpha", "to": "acme.probe.alpha"}])
    with pytest.raises(compose.CompositionError) as exc:
        compose.validate_package(ext)
    assert "acme.probe.beta" in str(exc.value)
    assert "orphan" in str(exc.value).lower()


def test_validate_package_passes_when_all_wired(tmp_path) -> None:
    ext = _build_extension(tmp_path, [{"from": "acme.probe.alpha", "to": "acme.probe.beta"}])
    report = compose.validate_package(ext)
    assert report["packages"][0]["id"] == "acme.extension.probe"
