# URN: component:plan:train-interlocking:Projections:backend:application
# Runtime: python
# Purpose: Deterministic derived projections (train sequence, coverage, mermaid) (#1248).
"""Deterministic projections derived from an interlocking.

The interlocking is authoritative for the guarded route space; the train YAML is
authoritative for executable linear steps. These functions PROJECT — they never
mutate either source. Outputs (coverage.yaml, sequence.mmd) are byte-deterministic
so re-running produces identical files.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, List, Mapping

import yaml

from .digest import route_projection_digest
from .loader import InterlockingError, load_interlocking
from .models import Route, TrainInterlocking, TrainStep

__all__ = [
    "project_route_to_train_sequence",
    "build_coverage",
    "render_mermaid",
    "ensure_interlocking_projections",
]


def _train_file(interlocking: TrainInterlocking, route: Route) -> Path:
    root = interlocking.repo_root
    if root is None:
        raise InterlockingError(
            "cannot resolve train path: interlocking has no known repo root "
            "(load it from disk via load_interlocking)"
        )
    return root / route.train_path


def _load_train_steps(train_file: Path) -> List[TrainStep]:
    if not train_file.exists():
        raise InterlockingError(f"target train not found: {train_file}")
    data = yaml.safe_load(train_file.read_text(encoding="utf-8"))
    steps: List[TrainStep] = []
    for raw in data.get("sequence", []):
        steps.append(
            TrainStep(
                step=int(raw["step"]),
                intent=raw["intent"],
                sender=raw["from"],
                recipient=raw["to"],
                artifact=raw["artifact"],
            )
        )
    return steps


def project_route_to_train_sequence(
    interlocking: TrainInterlocking, route_id: str
) -> List[TrainStep]:
    """Project a route onto its target train's linear sequence of :class:`TrainStep`."""
    route = interlocking.route_by_id(route_id)
    if route is None:
        raise InterlockingError(
            f"unknown route {route_id!r} in {interlocking.interlocking_id!r}"
        )
    return _load_train_steps(_train_file(interlocking, route))


def build_coverage(interlocking: TrainInterlocking) -> dict:
    """Build the deterministic coverage projection mapping."""
    routes_cov = []
    for route in sorted(interlocking.routes, key=lambda r: r.route_id):
        steps = project_route_to_train_sequence(interlocking, route.route_id)
        computed = route_projection_digest(steps, route.projection.fields)
        routes_cov.append(
            {
                "route_id": route.route_id,
                "category": route.category,
                "category_digit": route.category_digit,
                "priority": route.priority,
                "guard_ref": route.guard_ref,
                "train_id": route.train_id,
                "expected_sequence_digest": route.projection.expected_sequence_digest,
                "computed_sequence_digest": computed,
                "projection_matches": computed
                == route.projection.expected_sequence_digest,
                "step_count": len(steps),
            }
        )
    return {
        "interlocking_id": interlocking.interlocking_id,
        "title": interlocking.title,
        "theme": interlocking.theme,
        "status": interlocking.status,
        "route_resolution_strategy": interlocking.route_resolution.strategy,
        "routes": routes_cov,
        "invariants": sorted(i.id for i in interlocking.invariants),
        "residuals": sorted(r.id for r in interlocking.residuals),
        "message_count": len(interlocking.messages),
    }


def render_mermaid(interlocking: TrainInterlocking) -> str:
    """Render a deterministic Mermaid sequence diagram for the interlocking."""
    alias_by_ref: dict[str, str] = {}
    lines: List[str] = ["sequenceDiagram"]
    for idx, lifeline in enumerate(interlocking.lifelines):
        alias = f"P{idx}"
        alias_by_ref[lifeline.ref] = alias
        lines.append(f"    participant {alias} as {lifeline.ref}")

    def _alias(ref: str) -> str:
        return alias_by_ref.get(ref, ref.replace(":", "_"))

    for msg in interlocking.messages:
        arrow = "->>" if msg.kind != "self" else "-)"
        lines.append(
            f"    {_alias(msg.sender)}{arrow}{_alias(msg.recipient)}: {msg.intent}"
        )

    for frag in interlocking.fragments:
        guards = list(frag.guards)
        head = guards[0] if guards else None
        head_label = f"{frag.id} [{head.id}]" if head else frag.id
        lines.append(f"    {frag.kind} {head_label}")
        if head is not None:
            lines.append(f"        note over P0: {head.expression}")
        for guard in guards[1:]:
            lines.append(f"    else [{guard.id}]")
            lines.append(f"        note over P0: {guard.expression}")
        lines.append("    end")

    return "\n".join(lines) + "\n"


def ensure_interlocking_projections(interlocking_id: str, root: Path | str) -> Path:
    """Generate coverage.yaml + sequence.mmd for ``interlocking_id`` under ``root``.

    Returns the generated projection directory
    (``plan/_trains/_interlockings/<id>/``). Outputs are byte-deterministic.
    """
    root = Path(root)
    slug = interlocking_id.split(":", 1)[-1]
    il_path = root / "plan" / "_trains" / "_interlockings" / f"{slug}.yaml"
    interlocking = load_interlocking(il_path)

    out_dir = il_path.parent / slug
    out_dir.mkdir(parents=True, exist_ok=True)

    coverage_yaml = yaml.safe_dump(
        build_coverage(interlocking),
        sort_keys=True,
        default_flow_style=False,
        allow_unicode=True,
    )
    (out_dir / "coverage.yaml").write_text(coverage_yaml, encoding="utf-8")
    (out_dir / "sequence.mmd").write_text(render_mermaid(interlocking), encoding="utf-8")
    return out_dir
