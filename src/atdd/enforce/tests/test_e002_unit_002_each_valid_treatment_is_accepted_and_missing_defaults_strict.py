# URN: test:reconcile-dispositions:E002-UNIT-002-each-valid-treatment-is-accepted-and-missing-defaults-strict
# Acceptance: acc:reconcile-dispositions:E002-UNIT-002-each-valid-treatment-is-accepted-and-missing-defaults-strict
# WMBT: wmbt:reconcile-dispositions:E002
# Phase: RED
# Layer: domain
# Assertion: behavioral
"""E002-UNIT-002 — each of the four valid treatments is accepted unchanged and a
node with no disposition defaults to strict."""
from __future__ import annotations

from pathlib import Path

import yaml

from atdd.enforce.conventions import rule_metadata


def _write_node(substrate_home: Path, rule_id: str, node: dict) -> None:
    ext_dir = substrate_home / ".atdd" / "extensions" / "pkg" / "1.0.0" / "conventions"
    ext_dir.mkdir(parents=True, exist_ok=True)
    (ext_dir / f"{rule_id}.convention.yaml").write_text(
        yaml.safe_dump(node), encoding="utf-8"
    )


def test_e002_unit_002_each_valid_treatment_is_accepted_and_missing_defaults_strict(tmp_path):
    for treatment in ("strict", "advisory", "suppress-and-clean", "documentation-only"):
        _write_node(tmp_path, "coder.demo.rule", {"metadata": {"disposition": treatment}})
        meta = rule_metadata(tmp_path, "coder.demo.rule")
        assert meta.disposition == treatment

    # A node with no disposition defaults to strict (in-vocabulary, unchanged).
    _write_node(tmp_path, "coder.demo.nodisp", {"metadata": {"severity": 2}})
    assert rule_metadata(tmp_path, "coder.demo.nodisp").disposition == "strict"
