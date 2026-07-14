# URN: component:plan:train-interlocking:Sanity:backend:application
# Runtime: python
# Purpose: Planner-time interlocking sanity checks shared by validators + the Confirm gate (#1249).
"""Interlocking *sanity* checks — the planner-time enforcement for issue #1249.

Each public ``*_violations`` function takes a parsed :class:`TrainInterlocking`
(plus the repo ``root`` when on-disk resolution is needed) and returns a list of
structured **evidence dicts**. Every dict's keys are a SUBSET of the
``failure_evidence`` declared by the rule's convention node — that contract is
proven by ``test_sequence_diagram_sanity`` and the evidence-contract test.

This module is the single source of truth for "is this interlocking sound?":

  * the planner validators (``atdd validate planner``) run it over the repo's
    declared interlockings, and
  * the Confirm gate (``plan_session.confirm``) runs it over the kept train
    units' interlockings, failing closed.

It builds on the stable #1248 API (load/validate/routing/projection/guards) and
adds the cross-checks #1248 does not own (home/registry, entrypoint shape,
payload typing + contract-body resolution, fragment/acceptance binding, WMBT
surfacing, structural-residual explicitness, and the Cargo boundary in YAML).

Stdlib + yaml only; no other-layer imports (boundaries §3.3).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Callable, Dict, List

import yaml

_log = logging.getLogger(__name__)

from .digest import route_projection_digest
from .discovery import INTERLOCKINGS_HOME, registry_entries
from .guards import GuardSyntaxError, parse_guard
from .loader import InterlockingError, target_train_category
from .models import TrainInterlocking
from .projections import project_route_to_train_sequence

__all__ = [
    "RULE_CHECKS",
    "rule_ids",
    "interlocking_violations",
    "home_violations",
    "entrypoint_shape_violations",
    "route_category_violations",
    "guard_grammar_violations",
    "route_resolution_violations",
    "guard_coverage_violations",
    "projection_equivalence_violations",
    "message_payload_typed_violations",
    "payload_contract_body_violations",
    "payload_contract_registered_violations",
    "fragment_acceptance_binding_violations",
    "wmbt_surface_or_residual_violations",
    "structural_residual_explicit_violations",
    "does_not_carry_cargo_violations",
]

# Field-name tokens that would smuggle Cargo runtime state into a YAML that is
# only allowed to SELECT routes and name contract identities (#1249 node 13).
_FORBIDDEN_CARGO_TOKENS = ("cargo", "train_result", "artifact_data", "artifact_value")


def _iid(il: TrainInterlocking) -> str:
    return il.interlocking_id


# --- 1. home / registry -----------------------------------------------------
def home_violations(il: TrainInterlocking, root: Path | str) -> List[dict]:
    """``planner.train.interlocking-home``: artifact under the canonical home and
    registered in the interlockings registry."""
    out: List[dict] = []
    loaded = il.loaded_from
    expected_home = INTERLOCKINGS_HOME
    if loaded is not None:
        try:
            rel = Path(loaded).resolve().relative_to(Path(root).resolve())
            actual_home = str(rel.parent)
        except ValueError:
            actual_home = str(Path(loaded).parent)
        if actual_home != expected_home:
            out.append({
                "interlocking_id": _iid(il),
                "path": str(loaded),
                "expected_home": expected_home,
                "actual_home": actual_home,
            })
    registered = {e.get("interlocking_id") for e in registry_entries(root)}
    if registered and il.interlocking_id not in registered:
        out.append({
            "interlocking_id": _iid(il),
            "path": il.source.path,
            "expected_home": expected_home,
            "actual_home": "absent from plan/_trains/_interlockings.yaml registry",
        })
    return out


# --- 2. entrypoint shape ----------------------------------------------------
def entrypoint_shape_violations(il: TrainInterlocking, root=None) -> List[dict]:
    ep = il.entrypoint
    out: List[dict] = []
    if ep.exposed and len(ep.actions) < 1:
        out.append({
            "interlocking_id": _iid(il),
            "exposed": True,
            "actions": list(ep.actions),
            "field_path": "entrypoint.actions",
        })
    if not ep.exposed and not ep.reason:
        out.append({
            "interlocking_id": _iid(il),
            "exposed": False,
            "reason": ep.reason,
            "field_path": "entrypoint.reason",
        })
    return out


# --- 3. route category matches train id -------------------------------------
def route_category_violations(il: TrainInterlocking, root=None) -> List[dict]:
    """``planner.train.interlocking-route-category-matches-train-id``: a route's
    declared ``category`` must agree with the ``category`` FIELD of the target
    train it selects (issue #1421).

    Category is a validated field on the train, never a digit embedded in the
    identity, so this is a field COMPARE — it does not parse ``train_id``. A route
    whose target train declares no category (unmigrated during transition) is not
    judged here. The reader is shared with the semantic validator, so both paths
    resolve the target train's category identically (#1440).
    """
    out: List[dict] = []
    for route in il.routes:
        train_category = target_train_category(route.train_path, root)
        if train_category is None:
            continue
        if route.category != train_category:
            out.append({
                "interlocking_id": _iid(il),
                "route_id": route.route_id,
                "category": route.category,
                "train_id": route.train_id,
                "train_category": train_category,
                "train_path": route.train_path,
            })
    return out


# --- 4. guard grammar -------------------------------------------------------
def guard_grammar_violations(il: TrainInterlocking, root=None) -> List[dict]:
    out: List[dict] = []
    for guard in il.guard_index().values():
        try:
            parse_guard(guard.expression)
        except GuardSyntaxError as exc:
            invalid = getattr(exc, "token", None)
            out.append({
                "interlocking_id": _iid(il),
                "guard_id": guard.id,
                "expression": guard.expression,
                "invalid_token": str(invalid) if invalid is not None else "",
                "reason": str(exc)[:160],
            })
    return out


# --- 5. route resolution deterministic --------------------------------------
def route_resolution_violations(il: TrainInterlocking, root=None) -> List[dict]:
    out: List[dict] = []
    strategy = il.route_resolution.strategy
    route_ids = [r.route_id for r in il.routes]
    priorities = [r.priority for r in il.routes]
    if strategy not in ("fail_on_multiple_match", "first_priority"):
        out.append({
            "interlocking_id": _iid(il),
            "strategy": strategy,
            "route_ids": route_ids,
            "priorities": priorities,
            "reason": "strategy is not an allowed deterministic strategy",
        })
    elif strategy == "first_priority" and len(set(priorities)) != len(priorities):
        out.append({
            "interlocking_id": _iid(il),
            "strategy": strategy,
            "route_ids": route_ids,
            "priorities": priorities,
            "reason": "first_priority requires unique integer priorities",
        })
    return out


# --- 6. guard coverage ------------------------------------------------------
def guard_coverage_violations(il: TrainInterlocking, root=None) -> List[dict]:
    out: List[dict] = []
    route_by_guard: Dict[str, List[str]] = {}
    for r in il.routes:
        route_by_guard.setdefault(r.guard_ref, []).append(r.route_id)
    residual_guards = {rsd.id for rsd in il.residuals if rsd.kind == "structural"}
    for guard_id in il.guard_index():
        routes = route_by_guard.get(guard_id, [])
        if len(routes) == 1:
            continue
        if not routes and guard_id in residual_guards:
            continue
        status = "uncovered" if not routes else "multiply-covered"
        out.append({
            "interlocking_id": _iid(il),
            "guard_id": guard_id,
            "route_id": routes[0] if routes else None,
            "coverage_status": status,
        })
    return out


# --- 7. projection equivalence ----------------------------------------------
def projection_equivalence_violations(il: TrainInterlocking, root: Path | str) -> List[dict]:
    out: List[dict] = []
    for route in il.routes:
        try:
            steps = project_route_to_train_sequence(il, route.route_id)
        except InterlockingError as exc:  # surfaced as evidence, never swallowed
            out.append({
                "interlocking_id": _iid(il),
                "route_id": route.route_id,
                "train_id": route.train_id,
                "step": None,
                "field": "projection",
                "expected": route.projection.expected_sequence_digest,
                "actual": f"projection failed: {str(exc)[:120]}",
            })
            continue
        computed = route_projection_digest(steps, route.projection.fields)
        if computed != route.projection.expected_sequence_digest:
            out.append({
                "interlocking_id": _iid(il),
                "route_id": route.route_id,
                "train_id": route.train_id,
                "step": None,
                "field": "sequence_digest",
                "expected": route.projection.expected_sequence_digest,
                "actual": computed,
            })
    return out


# --- 8. message payload typed -----------------------------------------------
def message_payload_typed_violations(il: TrainInterlocking, root=None) -> List[dict]:
    out: List[dict] = []
    for msg in il.messages:
        p = msg.payload
        if not p.contract and not p.no_payload_reason:
            out.append({
                "interlocking_id": _iid(il),
                "message_id": msg.id,
                "payload": p.contract,
                "reason": p.no_payload_reason,
            })
    return out


# --- 9. payload contract body required --------------------------------------
_CONTRACT_ID_PREFIX = "contract:"
_SCHEMA_SUFFIXES = (".schema.json", ".schema.yaml", ".schema.yml")


def _normalize_identity(identity: str) -> str:
    """Strip an optional leading ``contract:`` so a bare contract identity and the
    ``contract:``-prefixed ``$id`` form set by ``create_contract`` (#1330) compare
    equal — this resolver works either side of the #1330 boundary."""
    identity = (identity or "").strip()
    if identity.startswith(_CONTRACT_ID_PREFIX):
        identity = identity[len(_CONTRACT_ID_PREFIX):]
    return identity


def _convention_schema_path(contract: str) -> str:
    """The deterministic contract-file location for an identity, per
    ``planner.artifact-naming.contract-file-mapping``: colons and variant dots
    become directory separators —
    ``theme:seg:aspect.variant → contracts/theme/seg/aspect/variant.schema.json``.
    """
    ident = _normalize_identity(contract)
    parts = ident.replace(":", "/").replace(".", "/")
    return f"contracts/{parts}.schema.json"


def _schema_declared_id(path: Path) -> "str | None":
    """Read a schema body's declared ``$id`` (``None`` if unreadable or absent)."""
    try:
        text = path.read_text(encoding="utf-8")
        doc = json.loads(text) if path.suffix == ".json" else yaml.safe_load(text)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        # An unreadable / unparseable schema body simply does not declare a
        # resolvable $id; the payload-contract-body rule reports it as unresolved.
        _log.debug(
            "schema $id read skipped (unreadable contract body)",
            extra={
                "path": str(path),
                "error": str(exc).splitlines()[0][:120],
            },
        )
        return None
    if isinstance(doc, dict):
        sid = doc.get("$id")
        return sid if isinstance(sid, str) else None
    return None


def _iter_contract_schemas(root: Path):
    """Yield every contract schema body under any ``contracts/`` directory."""
    seen: "set[Path]" = set()
    for suffix in _SCHEMA_SUFFIXES:
        for path in root.glob(f"**/contracts/**/*{suffix}"):
            if path.is_file() and path not in seen:
                seen.add(path)
                yield path


def _contract_resolves(contract: str, root: Path) -> "tuple[bool, str]":
    """Resolve a payload contract *identity* to a schema body by ``$id``, not by a
    filename glob (#1314 item C).

    A contract ``a:b:c`` resolves iff some ``*.schema.{json,yaml,yml}`` under a
    ``contracts/`` directory declares a ``$id`` equal to the identity — normalizing
    an optional ``contract:`` prefix on either side (#1330). The deterministic
    convention path (where ``create_contract`` writes) is checked first; otherwise
    every contract body is scanned, so a correctly-identified but
    non-canonically-named file still resolves (kills the #244 leaf-mismatch false
    negative). A body whose ``$id`` differs never satisfies the identity (kills the
    old leaf-glob false positive). Returns
    ``(resolved, expected_convention_path)``.
    """
    target = _normalize_identity(contract)
    convention_path = _convention_schema_path(contract)

    # 1. Deterministic convention path — the location `create_contract` writes to.
    candidate = root / convention_path
    if candidate.is_file() and \
            _normalize_identity(_schema_declared_id(candidate) or "") == target:
        return True, convention_path

    # 2. $id scan — resolves a correctly-identified body at a non-canonical path.
    for path in _iter_contract_schemas(root):
        if _normalize_identity(_schema_declared_id(path) or "") == target:
            return True, str(path.relative_to(root))

    return False, convention_path


def payload_contract_body_violations(il: TrainInterlocking, root: Path | str) -> List[dict]:
    root = Path(root)
    out: List[dict] = []
    for msg in il.messages:
        contract = msg.payload.contract
        if not contract:
            continue
        resolved, expected = _contract_resolves(contract, root)
        if not resolved:
            out.append({
                "interlocking_id": _iid(il),
                "message_id": msg.id,
                "contract": contract,
                "expected_schema_path": expected,
            })
    return out


# --- 9b. payload contract registered (#1314 item E, capstone) ----------------
_CONTRACT_REGISTRY_PATH = "contracts/_contracts.yaml"


def _entry_identity(entry) -> "str | None":
    """The identity an entry declares, under any of the accepted spellings."""
    if not isinstance(entry, dict):
        return None
    ident = entry.get("identity") or entry.get("id") or entry.get("$id")
    return str(ident) if ident else None


def _registry_identities(contracts) -> "set[str]":
    """Normalized identities from a ``contracts:`` block — a list of entries, or a
    mapping keyed by identity whose entry may restate (or omit) it."""
    identities: "set[str]" = set()
    if isinstance(contracts, list):
        for entry in contracts:
            ident = _entry_identity(entry)
            if ident:
                identities.add(_normalize_identity(ident))
    elif isinstance(contracts, dict):
        for key, entry in contracts.items():
            identities.add(_normalize_identity(_entry_identity(entry) or str(key)))
    return identities


def _load_contract_registry(root: Path) -> "set[str]":
    """Return the set of registered contract identities from the authored
    ``contracts/_contracts.yaml`` registry (normalized: ``contract:`` stripped).

    The registry is the single source of truth for
    ``identity -> {path, theme, producers, consumers}``, authored by
    ``create_contract`` (#1330) and validated for coherence by #1332. Accepts
    either a list of entries under ``contracts:`` or a mapping keyed by identity
    (matching #1332's ``load_registry``). A missing or unparseable registry
    yields the empty set, so a declared ``payload.contract`` then fails closed
    (unregistered) rather than crashing. Stdlib + yaml only.
    """
    reg = root / _CONTRACT_REGISTRY_PATH
    if not reg.is_file():
        return set()
    try:
        doc = yaml.safe_load(reg.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        # A malformed registry is owned by the #1332 coherence validator, not
        # this rule; treat as empty so we fail closed instead of raising.
        _log.debug(
            "contract registry read skipped (unparseable)",
            extra={
                "path": str(reg),
                "error": str(exc).splitlines()[0][:120],
            },
        )
        return set()
    contracts = doc.get("contracts") if isinstance(doc, dict) else None
    return _registry_identities(contracts)


def payload_contract_registered_violations(il: TrainInterlocking, root: Path | str) -> List[dict]:
    """A message's declared ``payload.contract`` must be an authored/registered
    contract — a member of ``contracts/_contracts.yaml`` — not merely a file that
    resolves on disk. This binds the interlocking/route model to the contract
    layer (registry membership), complementing the body-resolution rule above
    (#1314 item C resolves the body by ``$id``; this rule, item E, enforces the
    identity is registered)."""
    root = Path(root)
    registered = _load_contract_registry(root)
    out: List[dict] = []
    for msg in il.messages:
        contract = msg.payload.contract
        if not contract:
            continue
        if _normalize_identity(contract) not in registered:
            out.append({
                "interlocking_id": _iid(il),
                "message_id": msg.id,
                "contract": contract,
                "registry_path": _CONTRACT_REGISTRY_PATH,
            })
    return out


# --- 10. fragment / acceptance binding --------------------------------------
def fragment_acceptance_binding_violations(il: TrainInterlocking, root=None) -> List[dict]:
    out: List[dict] = []
    for frag in il.fragments:
        if frag.acceptance_refs:
            continue
        guard_id = frag.guards[0].id if frag.guards else None
        out.append({
            "interlocking_id": _iid(il),
            "fragment_id": frag.id,
            "guard_id": guard_id,
            "acceptance_ref": None,
            "missing_side": "fragment-has-no-acceptance",
        })
    return out


# --- 11. WMBT surface or residual -------------------------------------------
def wmbt_surface_or_residual_violations(il: TrainInterlocking, root=None) -> List[dict]:
    """A WMBT obligation carried by an invariant must actually surface — i.e. the
    invariant asserts a real expression — or be carried by an explicit structural
    residual. A ``wmbt_ref`` on an invariant with no real assertion is a dangling
    obligation (it names a WMBT but enforces nothing)."""
    out: List[dict] = []
    residual_wmbts = {rsd.id for rsd in il.residuals if rsd.kind == "structural"}
    for inv in il.invariants:
        ref = inv.wmbt_ref
        if not ref:
            continue
        surfaced = bool(inv.expression and inv.expression.strip())
        if surfaced or ref in residual_wmbts:
            continue
        out.append({
            "interlocking_id": _iid(il),
            "wmbt_ref": ref,
            "surface_kind": "invariant",
            "residual_id": None,
            "coverage_status": "unsurfaced",
        })
    return out


# --- 12. structural residual explicit ---------------------------------------
def structural_residual_explicit_violations(il: TrainInterlocking, root=None) -> List[dict]:
    out: List[dict] = []
    for rsd in il.residuals:
        if rsd.acceptance_ref and rsd.validator_ref and rsd.reason:
            continue
        out.append({
            "interlocking_id": _iid(il),
            "residual_id": rsd.id,
            "acceptance_ref": rsd.acceptance_ref,
            "validator_ref": rsd.validator_ref,
            "reason": rsd.reason,
        })
    return out


# --- 13. does not carry cargo (in YAML) -------------------------------------
def _scan_cargo(obj, path: str, out: List[dict], iid: str) -> None:
    if isinstance(obj, list):
        for i, item in enumerate(obj):
            _scan_cargo(item, f"{path}[{i}]", out, iid)
        return
    if not isinstance(obj, dict):
        return
    for key, value in obj.items():
        norm = str(key).lower().replace("-", "_")
        if any(tok in norm for tok in _FORBIDDEN_CARGO_TOKENS):
            out.append({
                "interlocking_id": iid,
                "field_path": f"{path}.{key}",
                "forbidden_value_kind": norm,
            })
        _scan_cargo(value, f"{path}.{key}", out, iid)


def does_not_carry_cargo_violations(il: TrainInterlocking, root=None) -> List[dict]:
    out: List[dict] = []
    if il.loaded_from is None or not Path(il.loaded_from).is_file():
        return out
    try:
        raw = yaml.safe_load(Path(il.loaded_from).read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        # parse failure is owned by the loader/schema family, not this rule.
        _log.debug(
            "cargo scan skipped (unparseable interlocking yaml)",
            extra={
                "path": str(il.loaded_from),
                "error": str(exc).splitlines()[0][:120],
            },
        )
        return out
    _scan_cargo(raw, "interlocking", out, _iid(il))
    return out


# --- registry of rule_id -> checker -----------------------------------------
RULE_CHECKS: "Dict[str, Callable[..., List[dict]]]" = {
    "planner.train.interlocking-home": home_violations,
    "planner.train.interlocking-entrypoint-shape": entrypoint_shape_violations,
    "planner.train.interlocking-route-category-matches-train-id": route_category_violations,
    "planner.train.interlocking-guard-grammar": guard_grammar_violations,
    "planner.train.interlocking-route-resolution-deterministic": route_resolution_violations,
    "planner.train.interlocking-guard-coverage": guard_coverage_violations,
    "planner.train.interlocking-projection-equivalence": projection_equivalence_violations,
    "planner.train.interlocking-message-payload-typed": message_payload_typed_violations,
    "planner.train.interlocking-payload-contract-body-required": payload_contract_body_violations,
    "planner.train.interlocking-payload-contract-registered": payload_contract_registered_violations,
    "planner.train.interlocking-fragment-acceptance-binding": fragment_acceptance_binding_violations,
    "planner.train.interlocking-wmbt-surface-or-residual": wmbt_surface_or_residual_violations,
    "planner.train.interlocking-structural-residual-explicit": structural_residual_explicit_violations,
    "planner.train.interlocking-does-not-carry-cargo": does_not_carry_cargo_violations,
}


def rule_ids() -> List[str]:
    return list(RULE_CHECKS)


def interlocking_violations(
    il: TrainInterlocking, root: Path | str
) -> "Dict[str, List[dict]]":
    """Run every sanity rule against ``il``; return ``{rule_id: [evidence,...]}``
    keeping only rules that produced at least one violation."""
    found: Dict[str, List[dict]] = {}
    for rule_id, check in RULE_CHECKS.items():
        evidence = check(il, root)
        if evidence:
            found[rule_id] = evidence
    return found
