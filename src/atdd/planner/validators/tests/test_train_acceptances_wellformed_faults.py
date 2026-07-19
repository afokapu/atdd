"""Fault injection for ``planner.train.acceptances`` (#1548).

The real-repo baseline for this rule is 0 — but ONLY because no train declares
an ``acceptances:`` block yet (16 train specs, 0 with acceptances; the backfill
is #1551). A clean-baseline assertion over an empty selection is worthless: it
would pass just as happily against a validator that returns [] unconditionally.

So every one of the node's constraints is proven to FIRE here, against a train
written into tmp_path. If a constraint is ever silently dropped from
``_check_block``, the matching test below goes red.
"""

from __future__ import annotations

from pathlib import Path
from typing import List

import pytest
import yaml

from atdd.planner.validators.test_train_acceptances_wellformed import (
    _RULE,
    collect_violations,
)


VALID_URN = "acc:train:self-compliance:validate-lifecycle:idempotent-on-retry"


def _valid_acceptance() -> dict:
    return {
        "identity": {
            "urn": VALID_URN,
            "purpose": "re-running the train produces no duplicate side effects",
            "phase": "SMOKE",
        },
        "harness": {"type": "e2e"},
    }


def _write_train(root: Path, acceptances: List[dict]) -> Path:
    path = root / "plan" / "_trains" / "self-compliance" / "validate-lifecycle.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(
            {
                "train_id": "train:self-compliance:validate-lifecycle",
                "title": "Validate lifecycle",
                "description": "fixture train",
                "acceptances": acceptances,
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return path


# ---------------------------------------------------------------------------
# The selection is real
# ---------------------------------------------------------------------------


def test_a_wellformed_train_acceptance_is_clean(tmp_path):
    _write_train(tmp_path, [_valid_acceptance()])
    assert collect_violations(tmp_path) == []


def test_a_subject_nested_train_is_actually_reached(tmp_path):
    """Positive control for every 'clean' assertion in this file.

    The fixture writes to plan/_trains/<subject>/<slug>.yaml. If the walk ever
    regressed to a top-level glob, every clean assertion here would pass
    vacuously — so one deliberately-broken acceptance must be caught at that
    nested path.
    """
    _write_train(tmp_path, [{"identity": {"urn": "acc:nope", "phase": "SMOKE",
                                          "purpose": "x"}}])
    violations = collect_violations(tmp_path)
    assert violations, "nested train file was not walked at all"
    assert "self-compliance/validate-lifecycle.yaml" in violations[0].location


# ---------------------------------------------------------------------------
# Each constraint fires
# ---------------------------------------------------------------------------


def test_malformed_urn_is_caught(tmp_path):
    acc = _valid_acceptance()
    acc["identity"]["urn"] = "acc:train:self-compliance:validate-lifecycle"  # no leaf slug
    _write_train(tmp_path, [acc])

    (v,) = collect_violations(tmp_path)
    assert "does not match the acc grammar" in v.detail
    assert v.rule_id == _RULE.rule_id


def test_retired_untyped_urn_is_caught(tmp_path):
    """The pre-#1421 identity scheme must not pass as a train acceptance."""
    acc = _valid_acceptance()
    acc["identity"]["urn"] = "acc:0001-self-compliance-validate:idempotent-on-retry:extra"
    _write_train(tmp_path, [acc])

    (v,) = collect_violations(tmp_path)
    assert "does not match the acc grammar" in v.detail


def test_missing_purpose_is_caught(tmp_path):
    acc = _valid_acceptance()
    acc["identity"]["purpose"] = "   "
    _write_train(tmp_path, [acc])

    (v,) = collect_violations(tmp_path)
    assert "identity.purpose is empty" in v.detail


def test_bad_phase_is_caught(tmp_path):
    acc = _valid_acceptance()
    acc["identity"]["phase"] = "DONE"
    _write_train(tmp_path, [acc])

    (v,) = collect_violations(tmp_path)
    assert "identity.phase" in v.detail


def test_unmeasurable_acceptance_is_caught(tmp_path):
    """Neither harness.type nor a complete signal — unenforceable."""
    acc = _valid_acceptance()
    del acc["harness"]
    _write_train(tmp_path, [acc])

    (v,) = collect_violations(tmp_path)
    assert "unenforceable" in v.detail


def test_signal_alone_satisfies_measurability(tmp_path):
    """The invariant is EITHER/OR, not harness-only."""
    acc = _valid_acceptance()
    del acc["harness"]
    acc["signal"] = {"metric": "retry_latency_ms", "threshold": 250}
    _write_train(tmp_path, [acc])

    assert collect_violations(tmp_path) == []


def test_zero_threshold_is_not_read_as_absent(tmp_path):
    """`threshold: 0` is the common meaningful case ("zero duplicates").

    A truthiness check would read it as missing and wrongly report the
    acceptance as unenforceable.
    """
    acc = _valid_acceptance()
    del acc["harness"]
    acc["signal"] = {"metric": "duplicate_side_effects_on_retry", "threshold": 0}
    _write_train(tmp_path, [acc])

    assert collect_violations(tmp_path) == []


def test_half_declared_signal_is_caught(tmp_path):
    """metric without threshold is half-declared and must not satisfy §4.3."""
    acc = _valid_acceptance()
    del acc["harness"]
    acc["signal"] = {"metric": "duplicate_side_effects_on_retry"}
    _write_train(tmp_path, [acc])

    (v,) = collect_violations(tmp_path)
    assert "unenforceable" in v.detail


def test_top_level_id_is_caught(tmp_path):
    """`id:` at block top level is a second, silently-ignored identity."""
    acc = _valid_acceptance()
    acc["id"] = "AC-SMOKE-001"
    _write_train(tmp_path, [acc])

    (v,) = collect_violations(tmp_path)
    assert "forbidden" in v.detail


def test_identity_id_is_still_allowed(tmp_path):
    """The node forbids top-level `id:` only — identity.id is a human label."""
    acc = _valid_acceptance()
    acc["identity"]["id"] = "AC-SMOKE-001"
    _write_train(tmp_path, [acc])

    assert collect_violations(tmp_path) == []


# ---------------------------------------------------------------------------
# Robustness
# ---------------------------------------------------------------------------


def test_train_without_acceptances_is_clean(tmp_path):
    """`acceptances:` is OPTIONAL — its absence is not a violation."""
    path = tmp_path / "plan" / "_trains" / "self-compliance" / "validate-lifecycle.yaml"
    path.parent.mkdir(parents=True)
    path.write_text('train_id: "train:self-compliance:validate-lifecycle"\n', encoding="utf-8")

    assert collect_violations(tmp_path) == []


def test_malformed_yaml_does_not_mask_other_files(tmp_path):
    """One broken train file must not stop the walk."""
    broken = tmp_path / "plan" / "_trains" / "substrate" / "broken.yaml"
    broken.parent.mkdir(parents=True)
    broken.write_text("{[not: valid yaml", encoding="utf-8")

    acc = _valid_acceptance()
    acc["identity"]["phase"] = "DONE"
    _write_train(tmp_path, [acc])

    violations = collect_violations(tmp_path)
    assert len(violations) == 1
    assert "identity.phase" in violations[0].detail
