# URN: component:plan:train-interlocking:Loader:backend:application
# Runtime: python
# Purpose: Load + shape-validate an interlocking YAML into a typed model (#1248).
"""Load and shape-validate interlocking artifacts.

``load_interlocking`` parses the YAML, validates it against the canonical
JSON schema (shape only), and builds the immutable :class:`TrainInterlocking`
model. Semantic cross-checks live in :mod:`validate`; route evaluation in
:mod:`routing`; projections in :mod:`projections`.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

import jsonschema
import yaml

from .models import (
    Entrypoint,
    Fragment,
    Guard,
    Invariant,
    Lifeline,
    Message,
    Payload,
    Projection,
    Residual,
    Route,
    RouteResolution,
    Source,
    TrainInterlocking,
)

__all__ = ["InterlockingError", "load_interlocking", "schema_path", "load_schema"]

_SCHEMA_PATH = (
    Path(__file__).resolve().parent.parent / "schemas" / "train-interlocking.schema.json"
)


class InterlockingError(ValueError):
    """Raised when an interlocking document cannot be loaded or fails shape validation."""


def schema_path() -> Path:
    return _SCHEMA_PATH


def load_schema() -> dict:
    return json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))


def _infer_repo_root(path: Path) -> Path | None:
    for ancestor in path.resolve().parents:
        if (ancestor / "plan").is_dir():
            return ancestor
    return None


def _build_payload(raw: Mapping[str, Any]) -> Payload:
    return Payload(
        contract=raw.get("contract"),
        no_payload_reason=raw.get("no_payload_reason"),
    )


def _build_message(raw: Mapping[str, Any]) -> Message:
    return Message(
        id=raw["id"],
        kind=raw["kind"],
        sender=raw["from"],
        recipient=raw["to"],
        intent=raw["intent"],
        payload=_build_payload(raw.get("payload", {})),
        feature_refs=tuple(raw.get("feature_refs", []) or []),
    )


def _build_fragment(raw: Mapping[str, Any]) -> Fragment:
    return Fragment(
        id=raw["id"],
        kind=raw["kind"],
        guards=tuple(
            Guard(id=g["id"], expression=g["expression"]) for g in raw.get("guards", [])
        ),
        acceptance_refs=tuple(raw.get("acceptance_refs", []) or []),
    )


def _build_route(raw: Mapping[str, Any]) -> Route:
    proj = raw["projection"]
    fields = proj.get("fields")
    projection = Projection(
        expected_sequence_digest=proj["expected_sequence_digest"],
        fields=tuple(fields) if fields else ("step", "intent", "from", "to", "artifact"),
    )
    return Route(
        route_id=raw["route_id"],
        category=raw["category"],
        # RETIRED (#1421): category is a FIELD on the target train, not an identity
        # digit. The schema already dropped it from `required`; legacy YAMLs may
        # still carry one, so read it optionally rather than demanding it.
        category_digit=raw.get("category_digit", ""),
        priority=int(raw["priority"]),
        guard_ref=raw["guard_ref"],
        train_id=raw["train_id"],
        train_path=raw["train_path"],
        projection=projection,
    )


def _from_dict(data: Mapping[str, Any], loaded_from: Path | None) -> TrainInterlocking:
    src = data["source"]
    ep = data["entrypoint"]
    return TrainInterlocking(
        schema_version=data["schema_version"],
        interlocking_id=data["interlocking_id"],
        title=data["title"],
        theme=data["theme"],
        status=data["status"],
        source=Source(path=src["path"], content_digest=src["content_digest"]),
        entrypoint=Entrypoint(
            exposed=bool(ep["exposed"]),
            actions=tuple(ep.get("actions", []) or []),
            reason=ep.get("reason"),
        ),
        route_resolution=RouteResolution(strategy=data["route_resolution"]["strategy"]),
        lifelines=tuple(Lifeline(ref=ll["ref"]) for ll in data["lifelines"]),
        messages=tuple(_build_message(m) for m in data.get("messages", [])),
        routes=tuple(_build_route(r) for r in data["routes"]),
        fragments=tuple(_build_fragment(f) for f in data.get("fragments", [])),
        invariants=tuple(
            Invariant(
                id=i["id"],
                expression=i["expression"],
                wmbt_ref=i.get("wmbt_ref"),
            )
            for i in data.get("invariants", [])
        ),
        residuals=tuple(
            Residual(
                id=r["id"],
                kind=r["kind"],
                reason=r["reason"],
                acceptance_ref=r.get("acceptance_ref"),
                validator_ref=r.get("validator_ref"),
            )
            for r in data.get("residuals", [])
        ),
        loaded_from=loaded_from,
        repo_root=_infer_repo_root(loaded_from) if loaded_from else None,
    )


def parse_interlocking(data: Mapping[str, Any]) -> TrainInterlocking:
    """Build a model from an already-parsed mapping (shape-validated first)."""
    jsonschema.validate(data, load_schema())
    return _from_dict(data, loaded_from=None)


def load_interlocking(path: Path | str) -> TrainInterlocking:
    """Load, shape-validate, and parse an interlocking YAML file."""
    path = Path(path)
    if not path.exists():
        raise InterlockingError(f"interlocking file not found: {path}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:  # pragma: no cover - exercised via malformed yaml
        raise InterlockingError(f"invalid YAML in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise InterlockingError(f"interlocking root must be a mapping: {path}")
    try:
        jsonschema.validate(data, load_schema())
    except jsonschema.ValidationError as exc:
        raise InterlockingError(
            f"interlocking {path} failed schema validation: {exc.message}"
        ) from exc
    return _from_dict(data, loaded_from=path)
