"""RED tests for WMBT E002 — disposition-vocabulary-validation (#1424).

Feature: feature:reconcile-dispositions:reconcile-dispositions

``rule_metadata`` must REJECT any convention node whose ``metadata.disposition``
is outside the treatment vocabulary {strict, advisory, suppress-and-clean,
documentation-only}, raising an error that names the offending value and the
allowed vocabulary. A missing disposition still defaults to ``strict``.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from atdd.enforce.conventions import (
    RuleMetadata,
    UnknownDispositionError,
    rule_metadata,
)
from atdd.enforce.dispositions import TREATMENT_DISPOSITIONS
from atdd.enforce.runner import _bound_conventions, resolve_substrate_home

_REPO_ROOT = Path(__file__).resolve().parents[4]


def _write_node(substrate_home: Path, rule_id: str, node: dict) -> None:
    ext_dir = substrate_home / ".atdd" / "extensions" / "pkg" / "1.0.0" / "conventions"
    ext_dir.mkdir(parents=True, exist_ok=True)
    (ext_dir / f"{rule_id}.convention.yaml").write_text(
        yaml.safe_dump(node), encoding="utf-8"
    )


# Acceptance: acc:reconcile-dispositions:E002-UNIT-001-out-of-vocabulary-disposition-is-rejected
def test_e002_unit_001_out_of_vocabulary_disposition_is_rejected(tmp_path):
    _write_node(tmp_path, "coder.demo.rule", {"metadata": {"disposition": "strick"}})

    with pytest.raises(UnknownDispositionError) as exc:
        rule_metadata(tmp_path, "coder.demo.rule")

    message = str(exc.value)
    assert "strick" in message  # names the offending value
    assert "documentation-only" in message  # names the allowed vocabulary


# Acceptance: acc:reconcile-dispositions:E002-UNIT-002-each-valid-treatment-is-accepted-and-missing-defaults-strict
def test_e002_unit_002_each_valid_treatment_is_accepted_and_missing_defaults_strict(tmp_path):
    for treatment in ("strict", "advisory", "suppress-and-clean", "documentation-only"):
        _write_node(tmp_path, "coder.demo.rule", {"metadata": {"disposition": treatment}})
        meta = rule_metadata(tmp_path, "coder.demo.rule")
        assert meta.disposition == treatment

    # A node with no disposition defaults to strict (in-vocabulary, unchanged).
    _write_node(tmp_path, "coder.demo.nodisp", {"metadata": {"severity": 2}})
    assert rule_metadata(tmp_path, "coder.demo.nodisp").disposition == "strict"


# Acceptance: acc:reconcile-dispositions:E002-SMOKE-001-every-vendored-node-declares-an-in-vocabulary-treatment
def test_e002_smoke_001_every_vendored_node_declares_an_in_vocabulary_treatment():
    """Reading the disposition of every bound convention node in the committed
    vendored substrate raises no vocabulary error — all are in-vocabulary."""
    substrate_home = resolve_substrate_home(_REPO_ROOT)
    bound = _bound_conventions(substrate_home)
    assert bound, "no bound conventions in the committed substrate — nothing to smoke"

    for conv in bound:
        rule_id = str(conv.get("convention_id"))
        meta = rule_metadata(substrate_home, rule_id)  # must not raise
        assert meta.disposition in TREATMENT_DISPOSITIONS, (
            f"{rule_id} declares out-of-vocabulary disposition {meta.disposition!r}"
        )
