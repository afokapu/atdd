# URN: component:plan:train-interlocking:SequenceDiagramSanity:backend:tests
# Runtime: python
# Purpose: Planner validators proving a train interlocking is complete, coherent, and projectable (#1249).
"""Planner interlocking sanity validators (issue #1249, parent #1246).

Each ``bind_rule(...)``-anchored test enforces one convention node under
``src/atdd/planner/conventions/nodes/planner.train.interlocking-*`` over the
repo's declared interlockings (``plan/_trains/_interlockings/*.yaml``). A repo
that declares no interlockings is vacuously sound, so the clean baseline is 0.

The fault-injection + evidence-contract tests construct the typed
:class:`TrainInterlocking` model directly (bypassing the JSON schema) so a single
malformed fact can be injected without writing a schema-invalid file, and prove
``set(emitted_evidence) <= set(node.validation.failure_evidence)`` for every rule.

Enforcement substrate: the ``validation.enforcement: confirm-blocking`` metadata
on each node makes these rules block ``atdd plan`` Confirm via the lifecycle, not
via a ``block`` disposition (the nodes are ``strict``); the runtime Confirm gate
lives in ``plan_session.confirm`` + ``test_confirm_interlocking_sanity``.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import List

import pytest
import yaml

from atdd.coach.utils.repo import find_repo_root
from atdd.coach.utils.rule_binding import bind_rule
from atdd.planner.interlocking import load_interlocking
from atdd.planner.interlocking.discovery import iter_interlocking_paths
from atdd.planner.interlocking.models import (
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
from atdd.planner.interlocking import sanity

pytestmark = [pytest.mark.platform]

_NODES_DIR = "src/atdd/planner/conventions/nodes"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _repo_interlockings(root: Path) -> List[TrainInterlocking]:
    out: List[TrainInterlocking] = []
    for path in iter_interlocking_paths(root):
        out.append(load_interlocking(path))
    return out


def _declared_failure_evidence(rule_id: str) -> set:
    """Read a rule node's ``validation.failure_evidence`` — the evidence contract."""
    root = find_repo_root()
    node_path = root / _NODES_DIR / f"{rule_id}.convention.yaml"
    doc = yaml.safe_load(node_path.read_text(encoding="utf-8"))
    return set((doc.get("validation") or {}).get("failure_evidence") or [])


def _assert_baseline_clean(rule_id: str) -> None:
    """Every declared interlocking in the real repo satisfies ``rule_id``."""
    root = find_repo_root()
    check = sanity.RULE_CHECKS[rule_id]
    for il in _repo_interlockings(root):
        evidence = check(il, root)
        assert evidence == [], f"{rule_id} violated by {il.interlocking_id}: {evidence}"


def _assert_evidence_shaped(rule_id: str, evidence: List[dict]) -> None:
    declared = _declared_failure_evidence(rule_id)
    assert evidence, f"{rule_id}: expected fault to be caught"
    for ev in evidence:
        assert set(ev).issubset(declared), (
            f"{rule_id}: emitted evidence {set(ev)} not subset of declared {declared}"
        )


# A self-consistent minimal interlocking the per-rule tests mutate (model-level,
# so a fault can be injected without a schema-invalid file).
def _valid_model(**overrides) -> TrainInterlocking:
    base = dict(
        schema_version="1.0.0",
        interlocking_id="interlocking:demo",
        title="Demo",
        theme="demo",
        status="draft",
        source=Source(path="plan/_trains/_interlockings/demo.yaml", content_digest="x"),
        entrypoint=Entrypoint(exposed=True, actions=("act",), reason=None),
        route_resolution=RouteResolution(strategy="first_priority"),
        lifelines=(Lifeline("wagon:a"), Lifeline("wagon:b")),
        messages=(
            Message(id="m1", kind="boundary", sender="wagon:a", recipient="wagon:b",
                    intent="do", payload=Payload(contract="demo:thing"), feature_refs=()),
        ),
        fragments=(
            Fragment(id="f1", kind="alt",
                     guards=(Guard("g0", "x == true"), Guard("g2", "y == true")),
                     acceptance_refs=("acc:demo",)),
        ),
        invariants=(Invariant(id="i1", expression="z <= 7", wmbt_ref="wmbt:demo"),),
        residuals=(Residual(id="r1", kind="structural", reason="ownership",
                            acceptance_ref="acc:demo", validator_ref="t::t"),),
        routes=(
            Route(route_id="nominal", category="nominal", category_digit="0", priority=1,
                  guard_ref="g0", train_id="0001-demo", train_path="plan/_trains/0001-demo.yaml",
                  projection=Projection(expected_sequence_digest="D")),
            Route(route_id="alternate", category="alternate", category_digit="2", priority=2,
                  guard_ref="g2", train_id="2001-demo", train_path="plan/_trains/2001-demo.yaml",
                  projection=Projection(expected_sequence_digest="D")),
        ),
    )
    base.update(overrides)
    return TrainInterlocking(**base)


# ---------------------------------------------------------------------------
# 1. home / registry
# ---------------------------------------------------------------------------
def test_interlocking_home_under_trains() -> None:
    rule = bind_rule("planner.train.interlocking-home")
    assert rule.rule_id == "planner.train.interlocking-home"
    _assert_baseline_clean(rule.rule_id)


def test_interlocking_home_fault_is_evidence_shaped(tmp_path: Path) -> None:
    bad = _valid_model(source=Source(path="elsewhere/demo.yaml", content_digest="x"))
    object.__setattr__(bad, "loaded_from", tmp_path / "elsewhere" / "demo.yaml")
    ev = sanity.home_violations(bad, tmp_path)
    _assert_evidence_shaped("planner.train.interlocking-home", ev)


# ---------------------------------------------------------------------------
# 2. entrypoint shape
# ---------------------------------------------------------------------------
def test_interlocking_entrypoint_shape_valid() -> None:
    rule = bind_rule("planner.train.interlocking-entrypoint-shape")
    _assert_baseline_clean(rule.rule_id)


def test_entrypoint_shape_fault_is_evidence_shaped() -> None:
    exposed_no_actions = _valid_model(entrypoint=Entrypoint(exposed=True, actions=(), reason=None))
    unexposed_no_reason = _valid_model(entrypoint=Entrypoint(exposed=False, actions=(), reason=None))
    _assert_evidence_shaped("planner.train.interlocking-entrypoint-shape",
                            sanity.entrypoint_shape_violations(exposed_no_actions))
    _assert_evidence_shaped("planner.train.interlocking-entrypoint-shape",
                            sanity.entrypoint_shape_violations(unexposed_no_reason))


# ---------------------------------------------------------------------------
# 3. route category matches train id
# ---------------------------------------------------------------------------
def test_interlocking_route_category_matches_train_id() -> None:
    rule = bind_rule("planner.train.interlocking-route-category-matches-train-id")
    _assert_baseline_clean(rule.rule_id)


def test_route_category_fault_is_evidence_shaped() -> None:
    bad_route = Route(route_id="nominal", category="nominal", category_digit="0", priority=1,
                      guard_ref="g0", train_id="1100-demo",  # train category digit 1 != nominal 0
                      train_path="plan/_trains/1100-demo.yaml",
                      projection=Projection(expected_sequence_digest="D"))
    bad = _valid_model(routes=(bad_route,))
    _assert_evidence_shaped("planner.train.interlocking-route-category-matches-train-id",
                            sanity.route_category_violations(bad))


# ---------------------------------------------------------------------------
# 4. guard grammar
# ---------------------------------------------------------------------------
def test_interlocking_guard_grammar_is_safe() -> None:
    rule = bind_rule("planner.train.interlocking-guard-grammar")
    _assert_baseline_clean(rule.rule_id)


def test_guard_grammar_fault_is_evidence_shaped() -> None:
    evil = Fragment(id="f1", kind="alt",
                    guards=(Guard("g0", "__import__('os').system('rm -rf /')"),),
                    acceptance_refs=("acc:demo",))
    bad = _valid_model(fragments=(evil,),
                       routes=(_valid_model().routes[0],))
    _assert_evidence_shaped("planner.train.interlocking-guard-grammar",
                            sanity.guard_grammar_violations(bad))


# ---------------------------------------------------------------------------
# 5. route resolution deterministic
# ---------------------------------------------------------------------------
def test_interlocking_route_resolution_strategy_declared() -> None:
    rule = bind_rule("planner.train.interlocking-route-resolution-deterministic")
    _assert_baseline_clean(rule.rule_id)


def test_no_ambiguous_interlocking_routes() -> None:
    """first_priority with duplicate priorities is non-deterministic -> caught."""
    dup = (
        Route(route_id="a", category="nominal", category_digit="0", priority=5,
              guard_ref="g0", train_id="0001-demo", train_path="plan/_trains/0001-demo.yaml",
              projection=Projection(expected_sequence_digest="D")),
        Route(route_id="b", category="alternate", category_digit="2", priority=5,
              guard_ref="g2", train_id="2001-demo", train_path="plan/_trains/2001-demo.yaml",
              projection=Projection(expected_sequence_digest="D")),
    )
    bad = _valid_model(routes=dup)
    _assert_evidence_shaped("planner.train.interlocking-route-resolution-deterministic",
                            sanity.route_resolution_violations(bad))


# ---------------------------------------------------------------------------
# 6. guard coverage
# ---------------------------------------------------------------------------
def test_every_executable_guard_projects_to_train() -> None:
    rule = bind_rule("planner.train.interlocking-guard-coverage")
    _assert_baseline_clean(rule.rule_id)


def test_guard_coverage_fault_is_evidence_shaped() -> None:
    # a third guard with no route and no structural residual -> uncovered.
    frag = Fragment(id="f1", kind="alt",
                    guards=(Guard("g0", "x == true"), Guard("g2", "y == true"),
                            Guard("gX", "w == true")),
                    acceptance_refs=("acc:demo",))
    bad = _valid_model(fragments=(frag,))
    _assert_evidence_shaped("planner.train.interlocking-guard-coverage",
                            sanity.guard_coverage_violations(bad))


# ---------------------------------------------------------------------------
# 7. projection equivalence
# ---------------------------------------------------------------------------
def test_train_sequence_matches_interlocking_projection() -> None:
    rule = bind_rule("planner.train.interlocking-projection-equivalence")
    _assert_baseline_clean(rule.rule_id)


def test_projection_equivalence_fault_is_evidence_shaped(tmp_path: Path) -> None:
    # missing train file -> projection cannot resolve -> caught, evidence-shaped.
    bad = _valid_model()
    object.__setattr__(bad, "repo_root", tmp_path)
    ev = sanity.projection_equivalence_violations(bad, tmp_path)
    _assert_evidence_shaped("planner.train.interlocking-projection-equivalence", ev)


# ---------------------------------------------------------------------------
# 8. message payload typed
# ---------------------------------------------------------------------------
def test_every_message_has_payload_contract_or_no_payload_reason() -> None:
    rule = bind_rule("planner.train.interlocking-message-payload-typed")
    _assert_baseline_clean(rule.rule_id)


def test_message_payload_fault_is_evidence_shaped() -> None:
    untyped = Message(id="m1", kind="boundary", sender="wagon:a", recipient="wagon:b",
                      intent="do", payload=Payload(contract=None, no_payload_reason=None))
    bad = _valid_model(messages=(untyped,))
    _assert_evidence_shaped("planner.train.interlocking-message-payload-typed",
                            sanity.message_payload_typed_violations(bad))


# ---------------------------------------------------------------------------
# 9. payload contract body required
# ---------------------------------------------------------------------------
def test_payload_contracts_have_schema_bodies() -> None:
    rule = bind_rule("planner.train.interlocking-payload-contract-body-required")
    _assert_baseline_clean(rule.rule_id)


def test_payload_contract_body_fault_is_evidence_shaped(tmp_path: Path) -> None:
    bad = _valid_model()  # contract 'demo:thing' resolves to nothing under tmp_path
    ev = sanity.payload_contract_body_violations(bad, tmp_path)
    _assert_evidence_shaped("planner.train.interlocking-payload-contract-body-required", ev)


def _write_contract_body(path: Path, schema_id: str) -> None:
    """Write a minimal contract schema body declaring ``$id`` at ``path``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"$id": schema_id, "type": "object"}), encoding="utf-8")


def _model_with_contract(contract: str) -> TrainInterlocking:
    msg = Message(id="m1", kind="boundary", sender="wagon:a", recipient="wagon:b",
                  intent="do", payload=Payload(contract=contract), feature_refs=())
    return _valid_model(messages=(msg,))


def test_payload_contract_resolves_by_id_not_filename(tmp_path: Path) -> None:
    """#1314 C / #244: a contract body whose FILENAME does not match the identity
    leaf still resolves when its ``$id`` is the contract identity. The prior
    leaf-glob (``**/contracts/**/result*.schema.*``) failed to find
    ``match_result.schema.json`` for ``match:result`` (leaf ``result`` ≠
    ``match_result``) — resolution is by identity, not filename."""
    _write_contract_body(tmp_path / "contracts" / "domain" / "match_result.schema.json",
                         "contract:match:result")
    model = _model_with_contract("match:result")
    assert sanity.payload_contract_body_violations(model, tmp_path) == []


def test_payload_contract_rejects_filename_glob_with_wrong_id(tmp_path: Path) -> None:
    """#1314 C: a body whose FILENAME globs the identity leaf but whose ``$id`` is a
    DIFFERENT identity must NOT satisfy the contract. The old leaf-glob passed it
    (false positive); identity resolution flags it as unresolved."""
    _write_contract_body(tmp_path / "contracts" / "domain" / "result_other.schema.json",
                         "contract:other:thing")
    model = _model_with_contract("match:result")
    ev = sanity.payload_contract_body_violations(model, tmp_path)
    assert ev, "a body with a non-matching $id must not satisfy the contract identity"
    _assert_evidence_shaped("planner.train.interlocking-payload-contract-body-required", ev)


# ---------------------------------------------------------------------------
# 9b. payload contract registered (#1333, capstone of #1314) — a message's
# declared payload.contract must be an AUTHORED/REGISTERED contract in the
# contracts registry (contracts/_contracts.yaml, maintained by #1330/#1332),
# not merely a file that glob-matches. This binds the interlocking/route model
# to the contract layer (registry membership), complementing the body-resolution
# rule above (#1331 resolves the body on disk; this rule enforces the identity
# is registered).
# ---------------------------------------------------------------------------
def _write_contract_registry(root: Path, identities: List[str]) -> None:
    """Author a minimal contracts/_contracts.yaml under *root* registering the
    given contract identities (the #1330/#1332 registry shape:
    identity -> path/theme/producers/consumers)."""
    reg_dir = root / "contracts"
    reg_dir.mkdir(parents=True, exist_ok=True)
    entries = [
        {"identity": ident, "path": f"contracts/{ident.replace(':', '/')}.schema.json",
         "theme": ident.split(":")[0], "producers": [], "consumers": []}
        for ident in identities
    ]
    (reg_dir / "_contracts.yaml").write_text(
        yaml.safe_dump({"contracts": entries}), encoding="utf-8"
    )


def test_payload_contracts_are_registered() -> None:
    rule = bind_rule("planner.train.interlocking-payload-contract-registered")
    assert rule.rule_id == "planner.train.interlocking-payload-contract-registered"
    _assert_baseline_clean(rule.rule_id)


def test_payload_contract_registered_pass_when_registered(tmp_path: Path) -> None:
    """A message whose payload.contract IS in the registry emits no violation."""
    _write_contract_registry(tmp_path, ["demo:thing"])
    ok = _valid_model()  # message m1 declares payload.contract == 'demo:thing'
    ev = sanity.payload_contract_registered_violations(ok, tmp_path)
    assert ev == [], f"registered contract should not violate, got {ev}"


def test_payload_contract_registered_fault_is_evidence_shaped(tmp_path: Path) -> None:
    """A message whose payload.contract is absent from the registry is caught,
    evidence-shaped. tmp_path has no contracts/_contracts.yaml, so 'demo:thing'
    is unregistered -> fail-closed violation."""
    bad = _valid_model()
    ev = sanity.payload_contract_registered_violations(bad, tmp_path)
    _assert_evidence_shaped("planner.train.interlocking-payload-contract-registered", ev)


# ---------------------------------------------------------------------------
# 10. fragment / acceptance binding
# ---------------------------------------------------------------------------
def test_guarded_fragments_bind_acceptances() -> None:
    rule = bind_rule("planner.train.interlocking-fragment-acceptance-binding")
    _assert_baseline_clean(rule.rule_id)


def test_fragment_binding_fault_is_evidence_shaped() -> None:
    unbound = Fragment(id="f1", kind="alt", guards=(Guard("g0", "x == true"),
                                                    Guard("g2", "y == true")),
                       acceptance_refs=())
    bad = _valid_model(fragments=(unbound,))
    _assert_evidence_shaped("planner.train.interlocking-fragment-acceptance-binding",
                            sanity.fragment_acceptance_binding_violations(bad))


# ---------------------------------------------------------------------------
# 11. WMBT surface or residual
# ---------------------------------------------------------------------------
def test_every_wmbt_surfaces_or_is_structural_residual() -> None:
    rule = bind_rule("planner.train.interlocking-wmbt-surface-or-residual")
    _assert_baseline_clean(rule.rule_id)


def test_wmbt_surface_fault_is_evidence_shaped() -> None:
    dangling = Invariant(id="i1", expression="", wmbt_ref="wmbt:demo")
    bad = _valid_model(invariants=(dangling,), residuals=())
    _assert_evidence_shaped("planner.train.interlocking-wmbt-surface-or-residual",
                            sanity.wmbt_surface_or_residual_violations(bad))


# ---------------------------------------------------------------------------
# 12. structural residual explicit
# ---------------------------------------------------------------------------
def test_structural_residuals_have_acceptance_and_validator() -> None:
    rule = bind_rule("planner.train.interlocking-structural-residual-explicit")
    _assert_baseline_clean(rule.rule_id)


def test_structural_residual_fault_is_evidence_shaped() -> None:
    weak = Residual(id="r1", kind="structural", reason="x",
                    acceptance_ref=None, validator_ref=None)
    bad = _valid_model(residuals=(weak,))
    _assert_evidence_shaped("planner.train.interlocking-structural-residual-explicit",
                            sanity.structural_residual_explicit_violations(bad))


# ---------------------------------------------------------------------------
# 13. does not carry cargo (in YAML)
# ---------------------------------------------------------------------------
def test_interlocking_schema_rejects_cargo_runtime_values(tmp_path: Path) -> None:
    rule = bind_rule("planner.train.interlocking-does-not-carry-cargo")
    _assert_baseline_clean(rule.rule_id)
    # a YAML carrying a forbidden Cargo runtime field is caught, evidence-shaped.
    il_dir = tmp_path / "plan" / "_trains" / "_interlockings"
    il_dir.mkdir(parents=True)
    il_file = il_dir / "demo.yaml"
    il_file.write_text(yaml.safe_dump({"interlocking_id": "interlocking:demo",
                                       "routes": [{"cargo": {"value": 1}}]}))
    bad = _valid_model()
    object.__setattr__(bad, "loaded_from", il_file)
    _assert_evidence_shaped("planner.train.interlocking-does-not-carry-cargo",
                            sanity.does_not_carry_cargo_violations(bad))
