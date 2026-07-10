# URN: test:reconcile-dispositions:E002-UNIT-001-out-of-vocabulary-disposition-is-rejected
# Acceptance: acc:reconcile-dispositions:E002-UNIT-001-out-of-vocabulary-disposition-is-rejected
# WMBT: wmbt:reconcile-dispositions:E002
# Phase: RED
# Layer: domain
# Assertion: behavioral
"""E002-UNIT-001 — a convention node whose metadata.disposition is outside the
treatment vocabulary is rejected with an error naming the value and the allowed
set."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from atdd.enforce.conventions import UnknownDispositionError, rule_metadata


def _write_node(substrate_home: Path, rule_id: str, node: dict) -> None:
    ext_dir = substrate_home / ".atdd" / "extensions" / "pkg" / "1.0.0" / "conventions"
    ext_dir.mkdir(parents=True, exist_ok=True)
    (ext_dir / f"{rule_id}.convention.yaml").write_text(
        yaml.safe_dump(node), encoding="utf-8"
    )


def test_e002_unit_001_out_of_vocabulary_disposition_is_rejected(tmp_path):
    _write_node(tmp_path, "coder.demo.rule", {"metadata": {"disposition": "strick"}})

    with pytest.raises(UnknownDispositionError) as exc:
        rule_metadata(tmp_path, "coder.demo.rule")

    message = str(exc.value)
    assert "strick" in message  # names the offending value
    assert "documentation-only" in message  # names the allowed vocabulary
