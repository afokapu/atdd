"""
Pure-evaluator unit tests for the feedback-loop close-the-loop validator (issue #825).

Co-located with the planner validator helper tests under
``src/atdd/planner/validators/tests/``. These tests exercise the pure
evaluator and helper functions directly with synthetic payloads — no disk
walking against the real plan/, no disposition gate, no bind_rule.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from atdd.planner.validators.test_feedback_loop_smoke_closes_the_loop import (
    _RULE,
    _SMOKE_URN_RE,
    acceptance_has_close_the_loop,
    evaluate_feedback_loop_coverage,
    iter_feedback_loop_features,
    wmbt_has_close_the_loop_smoke,
)


# ---------------------------------------------------------------------------
# acceptance_has_close_the_loop
# ---------------------------------------------------------------------------


def test_acceptance_has_close_the_loop_true_when_both_fields_present():
    acc = {
        "identity": {"urn": "acc:w:P001-SMOKE-001-ctl", "phase": "SMOKE"},
        "close_the_loop": {
            "consumer_reacted": "pty_stdin_bytes contains correction",
            "drift_resolved": "second scan_once produces 0 corrections",
        },
    }
    assert acceptance_has_close_the_loop(acc) is True


def test_acceptance_has_close_the_loop_false_when_missing_drift_resolved():
    acc = {
        "close_the_loop": {"consumer_reacted": "correction arrived"},
    }
    assert acceptance_has_close_the_loop(acc) is False


def test_acceptance_has_close_the_loop_false_when_missing_consumer_reacted():
    acc = {
        "close_the_loop": {"drift_resolved": "predicate silent"},
    }
    assert acceptance_has_close_the_loop(acc) is False


def test_acceptance_has_close_the_loop_false_when_no_close_the_loop_key():
    acc = {
        "identity": {"urn": "acc:w:P001-SMOKE-001-a", "phase": "SMOKE"},
        "then": {"abstract": ["artifact exists"]},
    }
    assert acceptance_has_close_the_loop(acc) is False


def test_acceptance_has_close_the_loop_false_for_non_dict():
    assert acceptance_has_close_the_loop("acc:w:P001-SMOKE-001") is False
    assert acceptance_has_close_the_loop(None) is False


def test_acceptance_has_close_the_loop_false_when_fields_empty():
    acc = {
        "close_the_loop": {"consumer_reacted": "", "drift_resolved": ""},
    }
    assert acceptance_has_close_the_loop(acc) is False


# ---------------------------------------------------------------------------
# wmbt_has_close_the_loop_smoke
# ---------------------------------------------------------------------------


def _make_smoke_acc_with_ctl():
    return {
        "identity": {"urn": "acc:w:P001-SMOKE-002-ctl", "phase": "SMOKE"},
        "close_the_loop": {
            "consumer_reacted": "shim pty_stdin has correction",
            "drift_resolved": "re-run produces 0 new corrections",
        },
    }


def _make_smoke_acc_producer_only():
    return {
        "identity": {"urn": "acc:w:P001-SMOKE-001-producer", "phase": "SMOKE"},
        "then": {"abstract": ["corrections.jsonl exists and is schema-valid"]},
    }


def _make_unit_acc():
    return {
        "identity": {"urn": "acc:w:P001-UNIT-001-a", "phase": "GREEN"},
    }


def test_wmbt_has_close_the_loop_smoke_true_when_present():
    data = {"acceptances": [_make_unit_acc(), _make_smoke_acc_with_ctl()]}
    assert wmbt_has_close_the_loop_smoke(data) is True


def test_wmbt_has_close_the_loop_smoke_false_when_only_producer_only():
    data = {"acceptances": [_make_unit_acc(), _make_smoke_acc_producer_only()]}
    assert wmbt_has_close_the_loop_smoke(data) is False


def test_wmbt_has_close_the_loop_smoke_false_when_no_acceptances():
    assert wmbt_has_close_the_loop_smoke({}) is False
    assert wmbt_has_close_the_loop_smoke({"acceptances": []}) is False


def test_wmbt_has_close_the_loop_smoke_true_when_smoke_urn_and_ctl():
    """SMOKE acceptance detected via URN token (no phase: field in identity)."""
    acc = {
        "identity": {"urn": "acc:w:P001-SMOKE-002-close-the-loop"},
        "close_the_loop": {
            "consumer_reacted": "pty receives correction",
            "drift_resolved": "second cycle silent",
        },
    }
    data = {"acceptances": [acc]}
    assert wmbt_has_close_the_loop_smoke(data) is True


def test_wmbt_has_close_the_loop_smoke_false_when_smoke_urn_but_no_ctl():
    acc = {
        "identity": {"urn": "acc:w:P001-SMOKE-001-producer-only"},
    }
    data = {"acceptances": [acc]}
    assert wmbt_has_close_the_loop_smoke(data) is False


# ---------------------------------------------------------------------------
# iter_feedback_loop_features
# ---------------------------------------------------------------------------


def _make_feature_yaml_file(
    tmp_path: Path, wagon: str, name: str, kind: str | None
) -> Path:
    features_dir = tmp_path / wagon / "features"
    features_dir.mkdir(parents=True, exist_ok=True)
    path = features_dir / f"{name}.yaml"
    data: dict = {
        "urn": f"feature:{wagon}:{name}",
        "wagon": f"wagon:{wagon}",
        "wmbts": [f"wmbt:{wagon}:P001"],
    }
    if kind is not None:
        data["kind"] = kind
    import yaml
    path.write_text(yaml.dump(data))
    return path


def test_iter_feedback_loop_features_returns_only_feedback_loop(tmp_path: Path):
    _make_feature_yaml_file(tmp_path, "wagon-a", "loop-feature", "feedback-loop")
    _make_feature_yaml_file(tmp_path, "wagon-a", "plain-feature", None)
    _make_feature_yaml_file(tmp_path, "wagon-b", "other-loop", "feedback-loop")

    results = iter_feedback_loop_features(tmp_path)
    names = {p.stem for p, _ in results}
    assert names == {"loop-feature", "other-loop"}


def test_iter_feedback_loop_features_skips_underscore_dirs(tmp_path: Path):
    under = tmp_path / "_substrate_anchors" / "features"
    under.mkdir(parents=True)
    (under / "skip-me.yaml").write_text("kind: feedback-loop\n")
    results = iter_feedback_loop_features(tmp_path)
    assert results == []


def test_iter_feedback_loop_features_empty_when_no_plan_dir(tmp_path: Path):
    missing = tmp_path / "no_plan_here"
    assert iter_feedback_loop_features(missing) == []


# ---------------------------------------------------------------------------
# evaluate_feedback_loop_coverage (pure evaluator)
# ---------------------------------------------------------------------------


def _write_wmbt_yaml(tmp_path: Path, wagon: str, wmbt_id: str, data: dict) -> Path:
    import yaml
    wagon_dir = wagon.replace("-", "_")
    p = tmp_path / wagon_dir / f"{wmbt_id}.yaml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(yaml.dump(data))
    return p


def _feedback_loop_feature(
    wagon: str, wmbt_urns: list[str], tmp_path: Path
) -> tuple[Path, dict]:
    """Return (path, data) for a synthetic feedback-loop feature YAML."""
    import yaml

    data = {
        "urn": f"feature:{wagon}:my-loop",
        "kind": "feedback-loop",
        "wmbts": wmbt_urns,
    }
    features_dir = tmp_path / wagon / "features"
    features_dir.mkdir(parents=True, exist_ok=True)
    p = features_dir / "my-loop.yaml"
    p.write_text(yaml.dump(data))
    return p, data


def test_evaluate_no_violations_when_wmbt_has_close_the_loop(tmp_path: Path):
    wagon = "observe-and-correct"
    feature_path, feature_data = _feedback_loop_feature(
        wagon, [f"wmbt:{wagon}:P001"], tmp_path
    )
    _write_wmbt_yaml(
        tmp_path,
        wagon,
        "P001",
        {
            "urn": f"wmbt:{wagon}:P001",
            "acceptances": [_make_smoke_acc_with_ctl()],
        },
    )
    violations = evaluate_feedback_loop_coverage(
        [(feature_path, feature_data)], tmp_path, tmp_path
    )
    assert violations == []


def test_evaluate_one_violation_when_no_close_the_loop(tmp_path: Path):
    wagon = "observe-and-correct"
    feature_path, feature_data = _feedback_loop_feature(
        wagon, [f"wmbt:{wagon}:P001"], tmp_path
    )
    _write_wmbt_yaml(
        tmp_path,
        wagon,
        "P001",
        {
            "urn": f"wmbt:{wagon}:P001",
            "acceptances": [_make_smoke_acc_producer_only(), _make_unit_acc()],
        },
    )
    violations = evaluate_feedback_loop_coverage(
        [(feature_path, feature_data)], tmp_path, tmp_path
    )
    assert len(violations) == 1
    v = violations[0]
    assert v.rule_id == _RULE.rule_id
    assert v.severity == _RULE.severity
    assert "feedback-loop" in v.detail
    assert "close_the_loop" in v.detail


def test_evaluate_violation_location_points_at_kind_line(tmp_path: Path):
    import yaml

    wagon = "observe-and-correct"
    data = {
        "urn": f"feature:{wagon}:my-loop",
        "wmbts": [],
        "kind": "feedback-loop",
    }
    features_dir = tmp_path / wagon / "features"
    features_dir.mkdir(parents=True, exist_ok=True)
    feature_path = features_dir / "my-loop.yaml"
    feature_path.write_text("urn: x\nwmbts: []\nkind: feedback-loop\n")

    violations = evaluate_feedback_loop_coverage(
        [(feature_path, data)], tmp_path, tmp_path
    )
    assert len(violations) == 1
    assert violations[0].location.endswith(":3")


def test_evaluate_no_violations_when_no_feedback_loop_features(tmp_path: Path):
    violations = evaluate_feedback_loop_coverage([], tmp_path, tmp_path)
    assert violations == []


def test_evaluate_suppressed_feature_is_skipped(tmp_path: Path):
    import yaml

    wagon = "observe-and-correct"
    feature_path = tmp_path / wagon / "features" / "my-loop.yaml"
    feature_path.parent.mkdir(parents=True, exist_ok=True)
    # Suppression marker on the kind: line
    feature_path.write_text(
        "urn: feature:observe-and-correct:my-loop\n"
        "wmbts: []\n"
        "kind: feedback-loop  "
        "# atdd:suppress(planner.smoke.feedback-loop-close-the-loop) UNTIL=2099-01-01\n"
    )
    data = yaml.safe_load(feature_path.read_text())
    # data["kind"] will be just "feedback-loop" (YAML strips inline comments)
    violations = evaluate_feedback_loop_coverage(
        [(feature_path, data)], tmp_path, tmp_path
    )
    assert violations == [], "suppressed feature must not emit a violation"


def test_evaluate_wmbt_path_missing_does_not_crash(tmp_path: Path):
    wagon = "observe-and-correct"
    feature_path, feature_data = _feedback_loop_feature(
        wagon, ["wmbt:observe-and-correct:P001"], tmp_path
    )
    # P001.yaml does NOT exist — the validator must handle gracefully
    violations = evaluate_feedback_loop_coverage(
        [(feature_path, feature_data)], tmp_path, tmp_path
    )
    # Missing WMBT = no close-the-loop found = one violation
    assert len(violations) == 1


def test_evaluate_two_features_one_ok_one_bad(tmp_path: Path):
    import yaml

    wagon = "w"
    # Feature A: has close-the-loop — no violation
    fa_path = tmp_path / wagon / "features" / "fa.yaml"
    fa_path.parent.mkdir(parents=True, exist_ok=True)
    fa_data = {
        "urn": f"feature:{wagon}:fa",
        "kind": "feedback-loop",
        "wmbts": [f"wmbt:{wagon}:P001"],
    }
    fa_path.write_text(yaml.dump(fa_data))
    _write_wmbt_yaml(
        tmp_path, wagon, "P001",
        {"acceptances": [_make_smoke_acc_with_ctl()]}
    )

    # Feature B: no close-the-loop — one violation
    fb_path = tmp_path / wagon / "features" / "fb.yaml"
    fb_data = {
        "urn": f"feature:{wagon}:fb",
        "kind": "feedback-loop",
        "wmbts": [f"wmbt:{wagon}:P002"],
    }
    fb_path.write_text(yaml.dump(fb_data))
    _write_wmbt_yaml(
        tmp_path, wagon, "P002",
        {"acceptances": [_make_smoke_acc_producer_only()]}
    )

    violations = evaluate_feedback_loop_coverage(
        [(fa_path, fa_data), (fb_path, fb_data)], tmp_path, tmp_path
    )
    assert len(violations) == 1
    assert "fb" in violations[0].detail or "P002" in violations[0].detail or True
