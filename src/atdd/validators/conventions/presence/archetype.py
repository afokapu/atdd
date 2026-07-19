"""Reusable graph-question archetype for the `presence` family (#1204).

Real-graph execution (#1212): the two presence templates exposed here run over
the REAL composed convention graph (``graph_loader.ConventionGraph`` of ``Node``
objects). ``config['variant']`` selects which presence question to run; each
variant returns failure-evidence dicts whose keys are a SUBSET of the template's
declared ``failure_evidence``.

The graph is the canonical substrate: most variants read ``Node.fields`` directly,
and the file-backed variants (theme-zero, rule-disposition allowlist, phase
machine, feedback-loop suppression markers) read their source file through
``graph.root`` — the same disk-anchored pattern the proven sentinels use
(``_support/sentinels.py`` reads schema/config/artifact files from ``graph.root``).
"""
from __future__ import annotations

import logging

import re

import yaml

from .._support.template_contract import TemplateContract

_log = logging.getLogger(__name__)

TEMPLATES = [
    TemplateContract(
        family_id='presence',
        template_id='required_field_presence',
        question='Does every eligible node declare the fields required by its convention/schema?',
        selector='nodes whose schema/kind declares required fields',
        traversal='node -> required_fields',
        invariant='every required field exists and is non-empty',
        auto_capture='a new node is included if its schema/kind declares required fields',
        failure_evidence=['node_id', 'missing_field', 'schema_id', 'node_location'],
    ),
    TemplateContract(
        family_id='presence',
        template_id='required_relationship_presence',
        question='Does every eligible node have a required outgoing relationship or child edge?',
        selector='nodes whose schema/kind declares required relationships',
        traversal='node -> required_relationship_type -> target nodes',
        invariant='required relationship target set is non-empty',
        auto_capture='a new node is included if its schema declares required relationships',
        failure_evidence=['node_id', 'missing_relationship', 'expected_target_kind', 'node_location'],
    ),
    TemplateContract(
        family_id='presence',
        template_id='conditional_requirement',
        question='If condition A is true on a node, does field/edge B exist?',
        selector='nodes declaring conditional requirements',
        traversal='node -> condition field/value -> required field/edge',
        invariant='if condition is true, required target exists',
        auto_capture='a new node is included if its schema declares conditional requirements',
        failure_evidence=['node_id', 'condition', 'missing_requirement', 'node_location'],
    ),
]

TEMPLATE_IDS = [t.template_id for t in TEMPLATES]


# ===========================================================================
# Real-graph evaluators (#1212). Each variant implements
# selector -> traversal -> invariant -> failure-evidence over real Node objects.
# ===========================================================================

_LEGAL_DISPOSITIONS = frozenset(
    {"strict", "suppress-and-clean", "advisory", "documentation-only"}
)

# Source files the file-backed variants read through ``graph.root``.
_THEME_CONVENTION = "src/atdd/planner/conventions/theme.convention.yaml"
_RULE_ID_CONVENTION = "src/atdd/coach/conventions/rule-id.convention.yaml"
_PHASE_MACHINE_CONVENTION = "src/atdd/coach/conventions/phase_machine.convention.yaml"
_PHASE_MACHINE_GATE_COMMAND = "atdd validate planner"

# Feedback-loop (conditional_requirement) recognisers — mirror the legacy
# validator (planner.smoke.feedback-loop-close-the-loop) so parity is exact.
_SMOKE_URN_RE = re.compile(
    r"^acc:[a-z][a-z0-9-]*:[DLPCEMYRK]\d{3}-SMOKE-\d{3}(?:-[a-z0-9-]+)?$"
)
# Acceptance well-formedness (required_field_presence) — a `then` line that is
# nothing but a placeholder token states no outcome a test could assert.
_PLACEHOLDER_RE = re.compile(r"^(tbd|todo|tba|n/?a|fixme|xxx|\?+|-+)$", re.IGNORECASE)
_MIN_OUTCOME_CHARS = 10

_FEEDBACK_LOOP_SUPPRESS_RE = re.compile(
    r"atdd:suppress\(planner\.smoke\.feedback-loop-close-the-loop\)"
    r"\s+UNTIL=\d{4}-\d{2}-\d{2}"
)


def _variant(config) -> str | None:
    if isinstance(config, dict):
        return config.get("variant")
    return getattr(config, "variant", None)


def _read_yaml(graph, rel_path: str) -> dict:
    """Parse a convention/source file relative to ``graph.root``.

    Returns ``{}`` when the graph has no root (in-memory fixture fragments that
    do not exercise file-backed variants) or the file is missing/unparseable.
    """
    root = getattr(graph, "root", None)
    if root is None:
        return {}
    path = root / rel_path
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        _log.debug("convention evaluator handled a recoverable error", extra={"error": str(exc)[:160]})
        return {}
    return data if isinstance(data, dict) else {}


# --- required_field_presence variants --------------------------------------
def _check_theme_zero_mandatory(graph) -> list:
    """The commons floor (theme digit 0) must be declared present in the
    canonical theme taxonomy: ``theme_zero_token == commons``,
    ``theme_zero_mandatory`` truthy, and a digit-0 theme resolving to commons.

    NOTE (parity): the legacy validator (``test_theme_zero_mandatory``) is a
    code-level invariant — it sets ``resolved['0'] = CANONICAL_THEME_0`` and then
    asserts equality against that same constant, so it is tautological and cannot
    be faulted by repo data (proven by its own
    ``test_override_cannot_remove_commons_floor``). This convention variant adds
    the real, data-level gate over ``theme.convention.yaml`` that legacy lacks.
    """
    tax = _read_yaml(graph, _THEME_CONVENTION).get("taxonomy") or {}
    token = tax.get("theme_zero_token")
    mandatory = tax.get("theme_zero_mandatory")
    digit0 = next(
        (t for t in (tax.get("themes") or [])
         if isinstance(t, dict) and str(t.get("digit")) == "0"),
        None,
    )
    resolved0 = None
    if isinstance(digit0, dict):
        name = digit0.get("name")
        if isinstance(name, str) and "${theme_zero_token}" in name and token:
            resolved0 = token
        else:
            resolved0 = name

    floor_present = (
        token == "commons" and bool(mandatory) and resolved0 == "commons"
    )
    if floor_present:
        return []
    return [{
        "node_id": "theme.taxonomy.commons-floor",
        "missing_field": "taxonomy.theme_zero_token=commons (mandatory commons floor)",
        "node_location": _THEME_CONVENTION,
    }]


def _direct_validator(ref) -> bool:
    """A DIRECT enforcer (a validator function / conventions variant), as opposed
    to a rule-id cross-reference that delegates enforcement to another rule."""
    return bool(ref) and (
        ref.startswith("test_") or "::" in ref or ref.startswith("conventions/")
    )


def _check_rule_has_disposition(graph) -> list:
    """Every ENFORCED rule must carry a legal ``disposition``. Scope mirrors the
    legacy validator (``test_rule_disposition_required``) plus the single-node model
    (#1225): a rule is in scope if its location is a ``migration.completed`` convention
    (``rule-id.convention.yaml``), OR it is a single-node ``nodes/`` rule/constraint that
    declares a DIRECT validator. Single-node nodes that delegate enforcement via a
    rule-id cross-reference, or that are principle/family/doc kinds, legitimately omit
    ``disposition`` and are skipped. Reads ``disposition`` from the top level OR from the
    single-node ``metadata`` block.
    """
    allowlist = set(
        (_read_yaml(graph, _RULE_ID_CONVENTION).get("migration") or {}).get("completed")
        or []
    )
    out = []
    for rule in graph.rules():
        is_single_node = "/conventions/nodes/" in rule.location
        in_scope = rule.location in allowlist or (
            is_single_node
            and rule.fields.get("kind") in ("rule", "constraint")
            and _direct_validator(rule.validator)
        )
        if not in_scope:
            continue
        meta = rule.fields.get("metadata") or {}
        disp = rule.fields.get("disposition")
        if disp is None:
            disp = meta.get("disposition")
        if disp is None:
            out.append({"node_id": rule.id, "missing_field": "disposition",
                        "node_location": rule.location})
        elif disp not in _LEGAL_DISPOSITIONS:
            out.append({"node_id": rule.id,
                        "missing_field": f"disposition (illegal value {disp!r})",
                        "node_location": rule.location})
    return out


def _check_rule_has_fix_hint(graph) -> list:
    """Presence-of-value: every rule that declares a ``fix_hint`` must carry a
    non-empty string.

    NOTE (parity): the legacy validator (``test_fix_hint_completeness``) checks
    fix-hint *completeness* (C1 placeholder-resolution / C2 deprecation), NOT
    presence — it explicitly skips rules without a fix_hint. The graph-native
    presence question and the legacy completeness question share NO common
    faultable case, so this variant is convention-only (see the variant test for
    the documented two-way divergence). Modeling "every rule must declare a
    fix_hint" is also infeasible on the real repo (125/152 rules carry none), so
    presence is scoped to fix_hint-declaring rules to keep the baseline honest.
    """
    out = []
    for rule in graph.rules():
        if "fix_hint" not in rule.fields:
            continue
        val = rule.fields.get("fix_hint")
        if not (isinstance(val, str) and val.strip()):
            out.append({"node_id": rule.id, "missing_field": "fix_hint",
                        "node_location": rule.location})
    return out


def _check_phase_machine_init_precommit_gate(graph) -> list:
    """The phase machine's INIT phase must declare a ``pre_commit_gate`` that
    invokes the planner validator. Mirrors the legacy validator
    (``test_phase_machine_init_pre_commit_gate``).
    """
    rel = _PHASE_MACHINE_CONVENTION
    data = _read_yaml(graph, rel)
    phases = data.get("phases")
    init = phases.get("INIT") if isinstance(phases, dict) else None
    gate = init.get("pre_commit_gate") if isinstance(init, dict) else None
    node_id = "phase_machine.phases.INIT"
    if not (isinstance(gate, str) and gate.strip()):
        return [{"node_id": node_id, "missing_field": "pre_commit_gate",
                 "node_location": rel}]
    if _PHASE_MACHINE_GATE_COMMAND not in gate:
        return [{"node_id": node_id,
                 "missing_field": f"pre_commit_gate (must invoke {_PHASE_MACHINE_GATE_COMMAND!r})",
                 "node_location": rel}]
    return []


def _abstract_prose(section) -> list:
    """The non-empty prose lines of an acceptance ``given``/``when``/``then``
    section's ``abstract`` field.

    ``when.abstract`` is documented as a string and ``given``/``then`` as arrays
    (``planner.acceptance.abstract-fields-required``), but the plan corpus carries
    multi-line ``when.abstract`` arrays too. Both forms are prose, so both are
    accepted here — this rule checks that the narrative is PRESENT, not which
    YAML shape carries it.
    """
    if not isinstance(section, dict):
        return []
    value = section.get("abstract")
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        return [x for x in value if isinstance(x, str) and x.strip()]
    return []


def _verifiable_outcome(lines: list) -> bool:
    """True when at least one ``then`` line states an outcome a generated test
    can assert — substantive prose rather than a bare placeholder token.

    A line like ``TBD`` or ``???`` names no observable outcome. The match is
    anchored to the WHOLE stripped line: prose that merely mentions a placeholder
    (``"... or marked TBD if the follow-on is not yet filed"``) is a real outcome
    and stays clean.
    """
    return any(
        len(line.strip()) >= _MIN_OUTCOME_CHARS and not _PLACEHOLDER_RE.match(line.strip())
        for line in lines
    )


def _missing_prose(acc: dict, acc_id: str, wmbt) -> list:
    """Sections of ONE acceptance whose Given/When/Then narrative is absent or empty."""
    return [{"node_id": acc_id,
             "missing_field": f"{section}.abstract",
             "node_location": wmbt.location}
            for section in ("given", "when", "then")
            if not _abstract_prose(acc.get(section))]


def _unverifiable_outcome(acc: dict, acc_id: str, wmbt) -> list:
    """ONE acceptance whose ``then`` prose is present but states no assertable outcome."""
    then_lines = _abstract_prose(acc.get("then"))
    if not then_lines or _verifiable_outcome(then_lines):
        return []
    return [{"node_id": acc_id,
             "missing_field": "then.abstract (no verifiable outcome)",
             "node_location": wmbt.location}]


def _acceptance_violations(acc: dict, wmbt) -> list:
    """The well-formedness violations of ONE acceptance: a missing/empty
    given/when/then narrative, and a ``then`` that states no verifiable outcome.
    """
    acc_id = (acc.get("identity") or {}).get("urn") or wmbt.id
    return _missing_prose(acc, acc_id, wmbt) + _unverifiable_outcome(acc, acc_id, wmbt)


def _check_acceptance_well_formed(graph) -> list:
    """Every acceptance declares Given/When/Then prose AND a verifiable outcome
    (``planner.acceptance.well-formed``, formerly ``planner.acceptance.complete``).

    Local shape only — this says nothing about whether the acceptance SET is
    complete for its WMBT, which is ``planner.coverage.every-wmbt-must-have``.
    """
    return [v
            for wmbt in graph.by_kind("wmbt")
            for acc in (wmbt.fields.get("acceptances") or [])
            if isinstance(acc, dict)
            for v in _acceptance_violations(acc, wmbt)]


_REQUIRED_FIELD_VARIANTS = {
    "theme_zero_mandatory": _check_theme_zero_mandatory,
    "rule_has_disposition": _check_rule_has_disposition,
    "rule_has_fix_hint": _check_rule_has_fix_hint,
    "phase_machine_init_precommit_gate": _check_phase_machine_init_precommit_gate,
    "acceptance_well_formed": _check_acceptance_well_formed,
}


def evaluate_required_field_presence(graph, config=None) -> list:
    variant = _variant(config)
    fn = _REQUIRED_FIELD_VARIANTS.get(variant)
    if fn is None:
        raise NotImplementedError(
            "presence/required_field_presence: no real-graph evaluator for variant "
            f"{variant!r} (supported: {sorted(_REQUIRED_FIELD_VARIANTS)})"
        )
    return fn(graph)


# --- conditional_requirement variants --------------------------------------
def _acceptance_is_smoke(acc: dict) -> bool:
    identity = acc.get("identity") or {}
    return (identity.get("phase") == "SMOKE"
            or bool(_SMOKE_URN_RE.match(str(identity.get("urn", "")))))


def _acceptance_closes_the_loop(acc: dict) -> bool:
    ctl = acc.get("close_the_loop")
    return (isinstance(ctl, dict)
            and bool(ctl.get("consumer_reacted")) and bool(ctl.get("drift_resolved")))


def _wmbt_has_close_the_loop_smoke(wmbt) -> bool:
    for acc in (wmbt.fields.get("acceptances") or []):
        if isinstance(acc, dict) and _acceptance_is_smoke(acc) and _acceptance_closes_the_loop(acc):
            return True
    return False


def _feature_suppressed(graph, feature) -> bool:
    """True if the feature's ``kind:`` line carries the inline suppression marker
    (legacy parity: ``_is_suppressed`` skips suppressed feedback-loop features)."""
    root = getattr(graph, "root", None)
    if root is None:
        return False
    try:
        text = (root / feature.location).read_text(encoding="utf-8")
    except OSError as exc:
        _log.debug("convention evaluator handled a recoverable error", extra={"error": str(exc)[:160]})
        return False
    for line in text.splitlines():
        if line.lstrip().startswith("kind:") and _FEEDBACK_LOOP_SUPPRESS_RE.search(line):
            return True
    return False


def _check_feedback_loop_close_the_loop(graph) -> list:
    """IF a feature declares ``kind: feedback-loop`` THEN at least one of its
    WMBTs must carry a SMOKE acceptance with a ``close_the_loop`` block
    (``consumer_reacted`` + ``drift_resolved``). Mirrors the legacy validator
    (``test_feedback_loop_smoke_closes_the_loop``), including suppression.
    """
    out = []
    for feature in graph.by_kind("feature"):
        if feature.fields.get("kind") != "feedback-loop":
            continue
        if _feature_suppressed(graph, feature):
            continue
        satisfied = any(
            (wmbt := graph.by_id(ref)) is not None and _wmbt_has_close_the_loop_smoke(wmbt)
            for ref in feature.refs
        )
        if not satisfied:
            out.append({
                "node_id": feature.id,
                "condition": "kind=feedback-loop",
                "missing_requirement": (
                    "SMOKE acceptance with close_the_loop{consumer_reacted,drift_resolved}"
                ),
                "node_location": feature.location,
            })
    return out


_CONDITIONAL_VARIANTS = {
    "feedback_loop_close_the_loop": _check_feedback_loop_close_the_loop,
}


def evaluate_conditional_requirement(graph, config=None) -> list:
    variant = _variant(config)
    fn = _CONDITIONAL_VARIANTS.get(variant)
    if fn is None:
        raise NotImplementedError(
            "presence/conditional_requirement: no real-graph evaluator for variant "
            f"{variant!r} (supported: {sorted(_CONDITIONAL_VARIANTS)})"
        )
    return fn(graph)


# Auto-discovered by ``_support.evaluators._real_evaluators`` — DO NOT edit
# ``_support/evaluators.py`` (decentralized fan-out, #1212).
REAL_EVALUATORS = {
    "required_field_presence": evaluate_required_field_presence,
    "conditional_requirement": evaluate_conditional_requirement,
}
