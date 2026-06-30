"""Projection tests: route->train sequence, coverage, mermaid (#1248)."""
from __future__ import annotations

import yaml

from atdd.planner.interlocking import (
    ensure_interlocking_projections,
    load_interlocking,
    project_route_to_train_sequence,
    route_projection_digest,
)
from atdd.planner.interlocking.tests._fixtures import write_tree


def test_project_route_returns_linear_train_steps(tmp_path):
    il = load_interlocking(write_tree(tmp_path))
    steps = project_route_to_train_sequence(il, "nominal-all-voted")
    assert [s.step for s in steps] == [1]
    s = steps[0]
    assert s.sender == "wagon:blitz"
    assert s.recipient == "wagon:player"
    assert s.artifact == "match:result"


def test_route_projection_digest_is_deterministic(tmp_path):
    il = load_interlocking(write_tree(tmp_path))
    steps = project_route_to_train_sequence(il, "nominal-all-voted")
    d1 = route_projection_digest(steps, ["step", "intent", "from", "to", "artifact"])
    d2 = route_projection_digest(steps, ["step", "intent", "from", "to", "artifact"])
    assert d1 == d2
    assert len(d1) == 64


def test_route_projection_digest_changes_with_field_selection(tmp_path):
    il = load_interlocking(write_tree(tmp_path))
    steps = project_route_to_train_sequence(il, "nominal-all-voted")
    full = route_projection_digest(steps, ["step", "intent", "from", "to", "artifact"])
    narrow = route_projection_digest(steps, ["step", "artifact"])
    assert full != narrow


def test_ensure_projections_writes_deterministic_outputs(tmp_path):
    write_tree(tmp_path)
    out_dir = ensure_interlocking_projections("interlocking:match-resolution", tmp_path)
    coverage = out_dir / "coverage.yaml"
    mermaid = out_dir / "sequence.mmd"
    assert coverage.exists()
    assert mermaid.exists()

    cov = yaml.safe_load(coverage.read_text(encoding="utf-8"))
    assert cov["interlocking_id"] == "interlocking:match-resolution"
    covered_routes = {r["route_id"] for r in cov["routes"]}
    assert covered_routes == {"nominal-all-voted", "alternate-timeout"}

    mmd = mermaid.read_text(encoding="utf-8")
    assert mmd.startswith("sequenceDiagram")
    assert "wagon:blitz" in mmd or "blitz" in mmd

    # determinism: regenerating yields byte-identical files
    cov_bytes_1 = coverage.read_bytes()
    mmd_bytes_1 = mermaid.read_bytes()
    ensure_interlocking_projections("interlocking:match-resolution", tmp_path)
    assert coverage.read_bytes() == cov_bytes_1
    assert mermaid.read_bytes() == mmd_bytes_1


def test_mermaid_renders_alt_fragment(tmp_path):
    write_tree(tmp_path)
    out_dir = ensure_interlocking_projections("interlocking:match-resolution", tmp_path)
    mmd = (out_dir / "sequence.mmd").read_text(encoding="utf-8")
    assert "alt" in mmd  # the quorum-or-timeout alt fragment is rendered
