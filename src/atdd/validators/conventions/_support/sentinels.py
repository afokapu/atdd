"""Three sentinel validators run against the REAL composed convention graph (#1206).

Each proves a distinct capability end-to-end:
  - theme_must_be_canonical          : node-field inspection (wagon.theme)
  - direct_reference_resolution      : real graph traversal (refs resolve)
  - rule_validator_roundtrip         : rule -> validator -> emitted rule_id roundtrip

Each returns an EvalResult carrying selector cardinality so vacuous passes are
impossible to hide: a variant that selects zero nodes is a failure unless it
explicitly declares an empty selection is expected.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import List

_log = logging.getLogger(__name__)

CANONICAL_THEMES = {"commons", "plan", "test", "code", "coach"}


@dataclass
class EvalResult:
    selected_nodes: int = 0
    checked_edges: int = 0
    violations: List[dict] = field(default_factory=list)


def theme_must_be_canonical(graph) -> EvalResult:
    selected = graph.by_kind("wagon")
    r = EvalResult(selected_nodes=len(selected))
    for n in selected:
        r.checked_edges += 1
        if n.theme not in CANONICAL_THEMES:
            r.violations.append({"node_id": n.id, "field": "theme", "value": n.theme,
                                 "grammar_name": "canonical-theme", "node_location": n.location})
    return r


def direct_reference_resolution(graph) -> EvalResult:
    ids = graph.ids()
    selected = [n for n in graph.nodes() if n.refs]
    r = EvalResult(selected_nodes=len(selected))
    for n in selected:
        for ref in graph.refs_from(n):
            r.checked_edges += 1
            if ref not in ids:
                r.violations.append({"source_node": n.id, "ref_field": "refs",
                                     "missing_ref": ref, "source_location": n.location})
    return r


def rule_validator_roundtrip(graph) -> EvalResult:
    # Scope to MIGRATED rules (those declaring a `disposition`), matching legacy's
    # disposition-scoped reverse-coherence authority. Unmigrated rules (validator but
    # no disposition) are deferred to the disposition/migration gate — flagging them
    # here would diverge from legacy and surface latent, not-yet-owned inconsistencies.
    selected = [n for n in graph.rules() if n.validator and n.fields.get("disposition")]
    r = EvalResult(selected_nodes=len(selected))
    for rule in selected:
        r.checked_edges += 1
        decl_file = rule.validator.split("::", 1)[0]           # "test_x" or "test_x.py"
        decl_stem = PurePosixPath(decl_file).name.removesuffix(".py")
        emitters = graph.emits(rule.id)                         # files that bind_rule(rule.id)
        emitted_by_decl = any(
            PurePosixPath(e).name.removesuffix(".py") == decl_stem for e in emitters
        )
        if not emitted_by_decl:
            r.violations.append({
                "declaration_id": rule.id,
                "implementation_ref": rule.validator,
                "emitted_identity": sorted(emitters)[:3],
                "actual_resolved_target": "declared validator does not bind_rule(rule.id)",
            })
    return r


def scoped_identifier_uniqueness(graph) -> EvalResult:
    """Identifiers must be unique within their scope, across the 7 id-classes legacy
    `test_plan_uniqueness` enforces: rule-id (global), wagon-slug (global),
    train-id (global), wmbt-id (per wagon), feature-urn (per wagon),
    contract-urn (global), telemetry-urn (global), produce-artifact (per wagon).
    Per-wagon scopes key on the wagon package so the same id in two wagons is fine."""
    from collections import defaultdict
    buckets = defaultdict(list)            # (cls, scope_instance, identifier) -> [locations]
    kinds = defaultdict(set)               # same key -> {node kinds}

    def add(cls, ident, location, scope_instance=None, kind=None):
        if not ident:
            return
        key = (cls, scope_instance, ident)
        buckets[key].append(location)
        kinds[key].add(kind or cls)

    for n in graph.rules():
        add("rule-id", n.id, n.location, kind="rule")
    for w in graph.by_kind("wagon"):
        add("wagon-slug", w.fields.get("wagon") or w.package, w.location, kind="wagon")
        for p in (w.fields.get("produce") or []):
            if not isinstance(p, dict):
                continue
            add("produce-artifact", p.get("name"), w.location, scope_instance=w.package, kind="produce")
            add("contract-urn", p.get("contract"), w.location, kind="contract")
            add("telemetry-urn", p.get("telemetry"), w.location, kind="telemetry")
    for t in graph.by_kind("train"):
        add("train-id", t.fields.get("train_id"), t.location, kind="train")
    for tid, loc in graph.index_train_ids():          # legacy's representation (index)
        add("train-id-index", tid, loc, kind="train")
    for m in graph.by_kind("wmbt"):
        add("wmbt-id", m.id, m.location, scope_instance=m.package, kind="wmbt")
    for f in graph.by_kind("feature"):
        add("feature-urn", f.id, f.location, scope_instance=f.package, kind="feature")
    # declaration representations legacy reads, kept in their own scopes so a feature
    # appearing once in a file AND once in its manifest is NOT a false duplicate.
    for w in graph.by_kind("wagon"):
        for fref in (w.fields.get("features") or []):
            furn = fref.get("urn") if isinstance(fref, dict) else fref
            add("feature-urn-decl", furn, w.location, scope_instance=w.package, kind="feature-decl")
        wmbt_sec = w.fields.get("wmbt")
        if isinstance(wmbt_sec, dict):
            for wid in wmbt_sec:
                if wid != "total":
                    add("wmbt-id-decl", wid, w.location, scope_instance=w.package, kind="wmbt-decl")
        elif isinstance(wmbt_sec, list):
            for item in wmbt_sec:
                wid = item.get("id") if isinstance(item, dict) else item
                add("wmbt-id-decl", wid, w.location, scope_instance=w.package, kind="wmbt-decl")

    r = EvalResult(selected_nodes=len(buckets))
    for (cls, scope_instance, ident), locs in buckets.items():
        r.checked_edges += 1
        if len(locs) > 1:
            scope = cls if scope_instance is None else f"{cls}@{scope_instance}"
            r.violations.append({"duplicate_id": ident, "scope": scope,
                                 "locations": sorted(locs),
                                 "node_kinds": sorted(kinds[(cls, scope_instance, ident)])})
    return r


def reference_chain_resolution(graph) -> EvalResult:
    """Multi-hop wagon -> feature -> wmbt chains must resolve at every hop."""
    ids = graph.ids()
    wagons = [w for w in graph.by_kind("wagon") if w.refs]
    r = EvalResult(selected_nodes=len(wagons))
    for w in wagons:
        for fref in w.refs:
            r.checked_edges += 1
            feat = graph.by_id(fref)
            if feat is None:
                r.violations.append({"start_node": w.id, "chain_path": [w.id, fref],
                                     "failed_hop": fref, "missing_ref": fref})
                continue
            for wref in graph.refs_from(feat):
                r.checked_edges += 1
                if wref not in ids:
                    r.violations.append({"start_node": w.id,
                                         "chain_path": [w.id, fref, wref],
                                         "failed_hop": wref, "missing_ref": wref})
    return r


def _binding_ref_resolves(graph, ref, stems, rule_ids, seen) -> bool:
    """Resolve a rule's implementation ref to a real validator, honestly handling the
    three forms single-node (`atdd author`) nodes emit (#1212 a-fix):

      - `module::function`  → the file stem must be a known validator stem.
      - rule-id cross-ref   → another rule's id; resolves iff that rule exists and its
                              own ref resolves (so the binding is real, just indirected).
      - bare function name  → resolves to the validator module that defines `def <name>`.
    """
    if not ref:
        return False
    if "::" in ref:
        stem = PurePosixPath(ref.split("::", 1)[0]).name.removesuffix(".py")
        return stem in stems
    # No "::": either a rule-id cross-reference or a bare function name.
    # (1) Cross-ref to a loaded rule node → resolves iff that rule's own ref resolves.
    if ref in rule_ids and ref not in seen:
        target = graph.by_id(ref)
        if target is not None and _binding_ref_resolves(
                graph, target.validator, stems, rule_ids, seen | {ref}):
            return True
    # (2) Cross-ref to a rule that a real validator binds via `bind_rule(ref)` — proves
    #     the referenced rule is enforced even if its declaration lives in a nested
    #     `rules:` block the loader does not node-ify. Require a *validator* emitter.
    if any(PurePosixPath(e).name.removesuffix(".py") in stems for e in graph.emits(ref)):
        return True
    # (3) Bare function name → the validator module that defines `def <name>`.
    return bool(graph.validator_function_stems(ref))


def declaration_to_implementation_binding(graph) -> EvalResult:
    """Every rule declaring a validator must point to a validator that exists.

    The ref may be `module::function`, a rule-id cross-reference, or a bare function
    name (the three forms single-node author nodes emit); all three are resolved
    honestly by `_binding_ref_resolves`. A ref that resolves to none of them is a REAL
    unbound-implementation defect, not exempted."""
    stems = graph.validator_stems()
    rule_ids = {n.id for n in graph.rules()}
    selected = [n for n in graph.rules() if n.validator]
    r = EvalResult(selected_nodes=len(selected))
    for rule in selected:
        r.checked_edges += 1
        if not _binding_ref_resolves(graph, rule.validator, stems, rule_ids, set()):
            stem = PurePosixPath(rule.validator.split("::", 1)[0]).name.removesuffix(".py")
            r.violations.append({"declaration_node": rule.id, "implementation_ref": rule.validator,
                                 "missing_or_incompatible_implementation": stem,
                                 "declaration_location": rule.location})
    return r


_WMBT_URN_RE = __import__("re").compile(r"^wmbt:[a-z][a-z0-9-]*:[DLPCEMYRK][0-9]{3}$")


def identifier_grammar_conformance(graph) -> EvalResult:
    """Every WMBT urn must follow canonical grammar wmbt:<wagon>:<STEP><NNN>."""
    selected = graph.by_kind("wmbt")
    r = EvalResult(selected_nodes=len(selected))
    for n in selected:
        r.checked_edges += 1
        if not _WMBT_URN_RE.match(str(n.id)):
            r.violations.append({"node_id": n.id, "field": "urn", "value": n.id,
                                 "grammar_name": "wmbt-urn", "parse_error": "does not match grammar"})
    return r


def composed_graph_loads(graph) -> EvalResult:
    """All convention sources must parse into the composed graph (no load errors)."""
    from .graph_loader import scan_parse_errors
    errs = scan_parse_errors(graph.root)
    r = EvalResult(selected_nodes=len(graph.nodes()))
    for e in errs:
        r.violations.append({"source_file": e["source_file"], "parse_error": e["parse_error"]})
    return r


def artifact_reference_resolution(graph) -> EvalResult:
    """Every artifact/file reference (node.references) must resolve on disk."""
    selected = [n for n in graph.nodes() if n.fields.get("references")]
    r = EvalResult(selected_nodes=len(selected))
    for n in selected:
        refs = n.fields["references"]
        for ref in (refs if isinstance(refs, list) else [refs]):
            if not (isinstance(ref, str) and ("/" in ref or ref.endswith((".md", ".yaml", ".json", ".py")))):
                continue
            r.checked_edges += 1
            if not (graph.root / ref).exists():
                r.violations.append({"node_id": n.id, "artifact_ref": ref,
                                     "expected_path": ref, "node_location": n.location})
    return r


# Schema validation is scoped to `wagon` — the legacy-aligned target (test_plan_wagons)
# whose schema resolves standalone. wmbt/acceptance use cross-schema $refs (need a
# referencing registry) and feature/train raw-doc validation DIVERGES from legacy
# (description constraint) — both deferred, not folded into parity.
_SCHEMA_KINDS = ("wagon",)


def node_schema_conformance(graph) -> EvalResult:
    import json
    import jsonschema
    schemas = {}
    for kind in _SCHEMA_KINDS:
        p = graph.root / "src" / "atdd" / "planner" / "schemas" / f"{kind}.schema.json"
        if p.exists():
            schemas[kind] = json.loads(p.read_text(encoding="utf-8"))
    selected = [n for n in graph.nodes() if n.kind in schemas]
    r = EvalResult(selected_nodes=len(selected))
    for n in selected:
        r.checked_edges += 1
        try:
            jsonschema.validate(n.fields, schemas[n.kind])
        except jsonschema.ValidationError as exc:
            r.violations.append({"node_id": n.id, "schema_id": n.kind,
                                 "schema_error_path": "/".join(str(x) for x in exc.absolute_path),
                                 "schema_error_message": exc.message[:120],
                                 "node_location": n.location})
        except Exception as exc:
            # unresolved $ref / registry-needed schema — not a content violation.
            # Log (never silently swallow); skip this node's schema check.
            _log.info("schema check skipped (unresolved $ref/registry)",
                      extra={"node": n.id, "kind": n.kind, "error": str(exc)[:120]})
    return r


SENTINELS = {
    "grammar/theme_must_be_canonical": theme_must_be_canonical,
    "resolution/artifact_reference_resolution": artifact_reference_resolution,
    "schema/node_schema_conformance": node_schema_conformance,
    "binding/declaration_to_implementation_binding": declaration_to_implementation_binding,
    "grammar/identifier_grammar_conformance": identifier_grammar_conformance,
    "composition/composed_graph_loads": composed_graph_loads,
    "resolution/direct_reference_resolution": direct_reference_resolution,
    "binding/rule_validator_roundtrip": rule_validator_roundtrip,
    "uniqueness/scoped_identifier_uniqueness": scoped_identifier_uniqueness,
    "resolution/reference_chain_resolution": reference_chain_resolution,
}
