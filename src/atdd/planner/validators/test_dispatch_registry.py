"""Validators for the declared dispatch registry plan/_dispatch.yaml (#1043 / #1034).

Two rules:
- ``planner.train.dispatch-map-is-registry``: the dispatch map is a DECLARED,
  schema-valid artifact (``artifact_urn -> train_id``). The TrainRunner reports a
  ``diverged`` result; the Station Master routes by reading this registry - never
  an imperative in-code map.
- ``planner.train.dispatch-composite-key-exceptional``: a composite
  ``(artifact_urn, discriminant) -> train_id`` key is permitted ONLY with a
  ``behavioral_difference`` justification, and the discriminant is exactly one
  field:value (the canonical case is commons:decision:escalation.cause, #1083).

BOUND (#1054): both rules are declared in ``train.convention.yaml``'s ``rules:``
block and wired through ``bind_rule()`` + ``assert_disposition_satisfied`` (strict
disposition). Behaviour-preserving: the ``check_*`` logic is unchanged; real-registry
violations now route through the disposition gate under their bound rule_ids.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional

from atdd.coach.utils.disposition_gate import assert_disposition_satisfied
from atdd.coach.utils.repo import find_repo_root
from atdd.coach.utils.rule_binding import bind_rule
from atdd.coach.validators._violation import Violation

_RULE_MAP = bind_rule("planner.train.dispatch-map-is-registry")
_RULE_COMPOSITE = bind_rule("planner.train.dispatch-composite-key-exceptional")
_VALIDATOR_ID = "dispatch_registry"


def check_entry_shape(entry: dict) -> Optional[str]:
    """Every dispatch entry routes a divergence artifact to a train."""
    if not isinstance(entry, dict):
        return f"dispatch entry must be a mapping, got {type(entry).__name__}"
    if not entry.get("artifact_urn") or not entry.get("train_id"):
        return f"dispatch entry missing artifact_urn/train_id: {entry!r}"
    return None


def check_composite_key_exceptional(entry: dict) -> Optional[str]:
    """A composite key (entry carries ``discriminant``) must be exactly one
    field:value AND carry a ``behavioral_difference`` justification."""
    if "discriminant" not in entry:
        return None
    urn = entry.get("artifact_urn", "<unknown>")
    disc = entry["discriminant"]
    if not isinstance(disc, dict) or len(disc) != 1:
        return (f"{urn}: composite `discriminant` must be exactly one field:value, "
                f"got {disc!r}")
    if not entry.get("behavioral_difference"):
        return (f"{urn}: composite key on {disc!r} requires a `behavioral_difference` "
                f"justification (dispatch-composite-key-exceptional)")
    return None


def _load_registry(repo_root: Path):
    try:
        import yaml
    except ImportError:  # pragma: no cover
        return None
    dpath = repo_root / "plan" / "_dispatch.yaml"
    if not dpath.is_file():
        return None
    return yaml.safe_load(dpath.read_text(encoding="utf-8"))


# --- real-registry: declared + schema-valid + well-formed entries ---

def test_real_dispatch_registry_is_declared_and_schema_valid():
    repo = find_repo_root()
    registry = _load_registry(repo)
    assert registry is not None, "plan/_dispatch.yaml must exist (declared registry)"
    assert isinstance(registry.get("dispatch"), list), "registry must have a `dispatch` list"
    schema_path = repo / "plan" / "_dispatch.schema.json"
    assert schema_path.is_file(), "plan/_dispatch.schema.json must exist"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    try:
        import jsonschema
    except ImportError:  # pragma: no cover
        return
    jsonschema.validate(registry, schema)  # raises on nonconformance


def test_real_dispatch_entries_well_formed():
    repo = find_repo_root()
    registry = _load_registry(repo) or {"dispatch": []}
    violations: List[Violation] = []
    for entry in registry.get("dispatch", []):
        loc = f"plan/_dispatch.yaml:{entry.get('artifact_urn', '<unknown>') if isinstance(entry, dict) else '<entry>'}"
        shape = check_entry_shape(entry)
        if shape:
            violations.append(Violation(
                rule_id=_RULE_MAP.rule_id, severity=_RULE_MAP.severity,
                location=loc, detail=shape,
                fix_hint_ref=getattr(_RULE_MAP, "fix_hint_ref", None),
            ))
        composite = check_composite_key_exceptional(entry) if isinstance(entry, dict) else None
        if composite:
            violations.append(Violation(
                rule_id=_RULE_COMPOSITE.rule_id, severity=_RULE_COMPOSITE.severity,
                location=loc, detail=composite,
                fix_hint_ref=getattr(_RULE_COMPOSITE, "fix_hint_ref", None),
            ))
    assert_disposition_satisfied(validator_id=_VALIDATOR_ID, violations=violations)


# --- unit fixtures: prove the composite-key rule ---

def test_simple_key_passes():
    assert check_composite_key_exceptional(
        {"artifact_urn": "x:y:z", "train_id": "0101-x"}
    ) is None


def test_composite_without_justification_is_flagged():
    assert check_composite_key_exceptional(
        {"artifact_urn": "commons:decision:escalation", "train_id": "0301-x",
         "discriminant": {"cause": "dangerous_action"}}
    ) is not None


def test_composite_with_justification_passes():
    assert check_composite_key_exceptional(
        {"artifact_urn": "commons:decision:escalation", "train_id": "0301-x",
         "discriminant": {"cause": "dangerous_action"},
         "behavioral_difference": "escalate-to-human resolution differs from a decider-retry"}
    ) is None


def test_multi_field_discriminant_is_flagged():
    assert check_composite_key_exceptional(
        {"artifact_urn": "x:y:z", "train_id": "0101-x",
         "discriminant": {"a": "1", "b": "2"}, "behavioral_difference": "x"}
    ) is not None


def test_entry_missing_train_id_is_flagged():
    assert check_entry_shape({"artifact_urn": "x:y:z"}) is not None
