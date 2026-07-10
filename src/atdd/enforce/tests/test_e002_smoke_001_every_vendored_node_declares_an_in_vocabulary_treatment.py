# URN: test:reconcile-dispositions:reconcile-dispositions:E002-SMOKE-001-every-vendored-node-declares-an-in-vocabulary-treatment
# Acceptance: acc:reconcile-dispositions:E002-SMOKE-001-every-vendored-node-declares-an-in-vocabulary-treatment
# WMBT: wmbt:reconcile-dispositions:E002
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""E002-SMOKE-001 — reading the disposition of every bound convention node in the
committed vendored substrate raises no vocabulary error (all in-vocabulary)."""
from __future__ import annotations

from pathlib import Path

from atdd.enforce.conventions import rule_metadata
from atdd.enforce.dispositions import TREATMENT_DISPOSITIONS
from atdd.enforce.runner import _bound_conventions, resolve_substrate_home

_REPO_ROOT = Path(__file__).resolve().parents[4]


def test_e002_smoke_001_every_vendored_node_declares_an_in_vocabulary_treatment():
    substrate_home = resolve_substrate_home(_REPO_ROOT)
    bound = _bound_conventions(substrate_home)
    assert bound, "no bound conventions in the committed substrate — nothing to smoke"

    for conv in bound:
        rule_id = str(conv.get("convention_id"))
        meta = rule_metadata(substrate_home, rule_id)  # must not raise
        assert meta.disposition in TREATMENT_DISPOSITIONS, (
            f"{rule_id} declares out-of-vocabulary disposition {meta.disposition!r}"
        )
