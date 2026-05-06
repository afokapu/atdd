# URN: component:govern-lifecycle:enforcement-substrate:spawn_harness:renderer:backend:domain
# Runtime: python
# Purpose: Render substrate spec v12 §8.2 spawn-harness blocks (wmbt/train/security) into spawn prompts.

"""Spawn-harness renderer (substrate spec v12 §8.2 — issue #417).

Produces the YAML body that coach v6 §7.1 splices into spawn prompts after
its existing ``conventions[].rules_in_scope`` block. The output is a
verbatim match for spec §8.2 lines 600–633 modulo URN substitution.

Rendering is intentionally hand-rolled (no PyYAML emit) for two reasons:

* The spec example pins block ordering, key ordering inside each rule,
  and quote-style. PyYAML's default emitter rearranges keys
  alphabetically and adds quotes that diverge from the reviewer-eye-
  trained shape. The hand-rolled emitter holds the example shape stable.
* The block is glued into a larger prompt template; emitting raw text is
  simpler than building a dict tree and post-processing PyYAML output.

Field-name mapping (issue #417 — short names per spec §8.2 example):

    Output key            ← RuleMetadata source
    --------------------    -------------------------
    purpose               ← description
    expectations          ← then (full list, one bullet per item)
    acceptance_urn        ← acceptance_urn        (WMBT/train rules)
    acceptance_ref        ← bound_acceptance_urn  (security rules)
    threat                ← description           (security rules)
    mitigation            ← fix_hint              (security rules)
    severity              ← severity              (security rules)
    security_urn          ← security_urn

The internal ``RuleMetadata`` field names ``bound_acceptance_urn``,
``description``, and ``then`` never appear in the rendered output.
"""
from __future__ import annotations

from typing import Iterable, List, Optional, Sequence, Tuple

from atdd.coach.utils.rule_binding import RuleMetadata


__all__ = [
    "render_spawn_blocks",
    "render_security_rules_block",
    "render_train_rules_block",
    "render_wmbt_rules_block",
]


# ---------------------------------------------------------------------------
# Scalar emit — minimal YAML-friendly quoting
# ---------------------------------------------------------------------------
# YAML scalars typically don't need quoting. The exceptions for our payload
# are strings that look like flow-style indicators or contain leading/trailing
# whitespace. Acceptance YAML upstream is hand-authored prose, so quoting is
# rarely necessary; when it is, double-quote with minimal escaping. Keeping
# this aligned with the spec example (which renders most prose unquoted)
# preserves byte-identity in the snapshot fixture.
_YAML_DANGEROUS_PREFIXES = ("- ", "? ", ": ", "*", "&", "!", "|", ">", "%", "@", "`")


def _emit_scalar(value: object) -> str:
    """Render *value* as a YAML scalar.

    Booleans / None / ints render unquoted. Strings render unquoted unless
    they collide with YAML's flow indicators or contain a leading/trailing
    space. The renderer never emits multi-line scalars (acceptance prose
    is always single-line).
    """
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    s = str(value)
    if not s:
        return '""'
    needs_quote = (
        s != s.strip()
        or s.startswith(_YAML_DANGEROUS_PREFIXES)
        or s.lower() in ("yes", "no", "true", "false", "null", "~")
        or ": " in s
        or s.startswith("# ")
    )
    if needs_quote:
        return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return s


def _filter_phase(rules: Iterable[RuleMetadata], phase: str) -> List[RuleMetadata]:
    """Return rules whose ``RuleMetadata.phase`` equals *phase*."""
    return [r for r in rules if r.phase == phase]


def _group_by(
    rules: Iterable[RuleMetadata], key: str
) -> List[Tuple[str, List[RuleMetadata]]]:
    """Group *rules* by attribute *key*, preserving first-seen order."""
    order: List[str] = []
    buckets: dict = {}
    for rule in rules:
        bucket_key = getattr(rule, key, None)
        if not bucket_key:
            continue
        if bucket_key not in buckets:
            buckets[bucket_key] = []
            order.append(bucket_key)
        buckets[bucket_key].append(rule)
    return [(k, buckets[k]) for k in order]


# ---------------------------------------------------------------------------
# Per-rule emitters
# ---------------------------------------------------------------------------
def _emit_acceptance_rule(rule: RuleMetadata, *, indent: int) -> List[str]:
    """Emit a single WMBT-or-train rule body (the ``- id: ...`` block).

    Indent is the column of the leading dash. Keys inside the rule sit at
    ``indent + 2``; ``expectations:`` bullets sit at ``indent + 4``.
    """
    pad = " " * indent
    inner = " " * (indent + 2)
    bullet_pad = " " * (indent + 4)
    lines = [f"{pad}- id: {_emit_scalar(rule.rule_id)}"]
    if rule.acceptance_urn:
        lines.append(f"{inner}acceptance_urn: {_emit_scalar(rule.acceptance_urn)}")
    lines.append(f"{inner}purpose: {_emit_scalar(rule.description)}")
    if rule.then:
        lines.append(f"{inner}expectations:")
        for expectation in rule.then:
            lines.append(f"{bullet_pad}- {_emit_scalar(expectation)}")
    return lines


def _emit_security_rule(rule: RuleMetadata, *, indent: int) -> List[str]:
    """Emit a single security rule body in spec §8.2 short-name shape."""
    pad = " " * indent
    inner = " " * (indent + 2)
    lines = [f"{pad}- id: {_emit_scalar(rule.rule_id)}"]
    if rule.security_urn:
        lines.append(f"{inner}security_urn: {_emit_scalar(rule.security_urn)}")
    lines.append(f"{inner}threat: {_emit_scalar(rule.description)}")
    if rule.fix_hint:
        lines.append(f"{inner}mitigation: {_emit_scalar(rule.fix_hint)}")
    if rule.severity is not None:
        lines.append(f"{inner}severity: {_emit_scalar(rule.severity)}")
    if rule.bound_acceptance_urn:
        # Note the rename: internal `bound_acceptance_urn` → output
        # `acceptance_ref` per issue #417 field-name pin.
        lines.append(
            f"{inner}acceptance_ref: {_emit_scalar(rule.bound_acceptance_urn)}"
        )
    return lines


# ---------------------------------------------------------------------------
# Block emitters — public
# ---------------------------------------------------------------------------
def render_wmbt_rules_block(
    rules: Iterable[RuleMetadata], *, coach_phase: str
) -> str:
    """Render the ``wmbt_rules:`` block for *coach_phase*.

    Filters *rules* to those carrying a ``wmbt_urn`` and a ``phase``
    matching *coach_phase*, then groups by ``wmbt_urn`` and emits one
    ``- wmbt_urn: ...\\n  rules:\\n  ...`` entry per WMBT.

    Returns an empty string (no block, no trailing newline) when no
    rules survive filtering.
    """
    eligible = [
        r for r in _filter_phase(rules, coach_phase) if r.wmbt_urn is not None
    ]
    if not eligible:
        return ""
    lines = ["wmbt_rules:"]
    for wmbt_urn, group in _group_by(eligible, "wmbt_urn"):
        lines.append(f"  - wmbt_urn: {_emit_scalar(wmbt_urn)}")
        lines.append("    rules:")
        for rule in group:
            lines.extend(_emit_acceptance_rule(rule, indent=6))
    return "\n".join(lines) + "\n"


def render_train_rules_block(
    rules: Iterable[RuleMetadata],
    *,
    coach_phase: str,
    train_scope: Sequence[str] = (),
) -> str:
    """Render the ``train_rules:`` block for *coach_phase*.

    *train_scope* is the explicit set of train URNs in scope, supplied
    by the caller (per issue #417 AC: full ``--scope train:<urn>,…``
    detection lands in a separate Track-F follow-up; this renderer
    accepts the scope set as input).

    Filters *rules* to those whose ``train_urn`` is in *train_scope*
    AND whose ``phase`` matches *coach_phase*. Groups by ``train_urn``.
    Returns an empty string when the block would be empty.
    """
    if not train_scope:
        return ""
    scope = set(train_scope)
    eligible = [
        r
        for r in _filter_phase(rules, coach_phase)
        if r.train_urn is not None and r.train_urn in scope
    ]
    if not eligible:
        return ""
    lines = ["train_rules:"]
    for train_urn, group in _group_by(eligible, "train_urn"):
        lines.append(f"  - train_urn: {_emit_scalar(train_urn)}")
        lines.append("    rules:")
        for rule in group:
            lines.extend(_emit_acceptance_rule(rule, indent=6))
    return "\n".join(lines) + "\n"


def render_security_rules_block(
    rules: Iterable[RuleMetadata], *, coach_phase: str
) -> str:
    """Render the ``security_rules:`` block for *coach_phase*.

    Per spec §8.1 paragraph 6 + §8.2 line 625, security rules carry no
    ``phase`` of their own — activation is determined by the BOUND
    acceptance's phase. Wiring that filter requires walking the
    acceptance graph from each security rule's ``bound_acceptance_urn``
    back to its acceptance phase.

    TODO(#422): wire the bound-acceptance phase resolver. Until that
    issue lands, this renderer emits every security rule whose
    ``security_urn`` is populated; the caller is responsible for
    pre-filtering. The block shape itself matches spec §8.2.
    """
    eligible = [r for r in rules if r.security_urn is not None]
    if not eligible:
        return ""
    lines = ["security_rules:"]
    for feature_urn, group in _group_by(eligible, "feature_urn"):
        lines.append(f"  - feature_urn: {_emit_scalar(feature_urn)}")
        lines.append("    rules:")
        for rule in group:
            lines.extend(_emit_security_rule(rule, indent=6))
    return "\n".join(lines) + "\n"


def render_spawn_blocks(
    rules: Iterable[RuleMetadata],
    *,
    coach_phase: str,
    train_scope: Sequence[str] = (),
) -> str:
    """Render all three substrate spawn-harness blocks, concatenated.

    Block order: ``wmbt_rules:``, ``train_rules:``, ``security_rules:``.
    Empty blocks are elided (no header, no separator). The output never
    has a leading or trailing blank line. Returns an empty string when
    no blocks would render — the coach can splice the empty result into
    a prompt without producing a stray section.
    """
    rules = list(rules)
    parts: List[str] = []
    wmbt = render_wmbt_rules_block(rules, coach_phase=coach_phase)
    if wmbt:
        parts.append(wmbt)
    train = render_train_rules_block(
        rules, coach_phase=coach_phase, train_scope=train_scope
    )
    if train:
        parts.append(train)
    security = render_security_rules_block(rules, coach_phase=coach_phase)
    if security:
        parts.append(security)
    return "".join(parts)
