# Component: component:atdd-plan-core:session-machine:UnitSpecSchemaGate:backend:domain
"""Schema validation for a plan session's hand-authored unit specs (#1929).

``atdd author`` promises schema-valid substrate artifacts BY CONSTRUCTION.
``atdd plan unit`` is the one layer where the spec is hand-authored — by a
person or an agent — and it made no such promise: ``Session.add_unit`` checked
ref/kind uniqueness and upsert semantics only. A Title-Case ``theme``, a prose
``subject`` or a ``wagon:``-prefixed ``primary_wagon`` was accepted at Compose,
survived every Ratify gate, and was written to ``plan/`` unread by any schema.

Two axes decide what this module does with a finding, and they are independent.

**Stage — well-formedness vs completeness.** Compose is a drafting loop:
``add_unit`` upserts by ``ref`` precisely so a spec can be re-stated as it fills
in, which its own docstring calls "the normal Compose loop (draft, look,
re-draft)". So Compose checks only whether the values that ARE present are
shaped right (``pattern``, ``enum``, ``type``, ``additionalProperties``) — those
are wrong the instant they are typed. The keywords that assert presence and size
(``required``, ``minItems``, ``minLength``, ``minProperties``) are stripped for
that pass and restored at Ratify, where the operator asserts "this exact unit
set may be authored" and an unfinished spec finally IS a defect. This split is
not an invention: ``planner.plan.session-lifecycle`` already defines Compose's
exit condition as "candidate decomposition convention-shaped".

**Tier — enforce vs advise.** Not every artifact schema describes the artifacts
atdd actually authors. Measured against this repo's own ``plan/`` tree,
``feature.schema.json`` rejects 134 of 188 real features and ``wmbt.schema.json``
294 of 468 real WMBTs — the latter says so in its own ``$comment``. Raising on
those would refuse the decomposition this repo ships, so they REPORT and the
findings ride on the unit; the honest schemas RAISE. A repo promotes a kind with

    plan:
      spec_validation:
        enforce: [feature, wmbt]

in ``.atdd/config.yaml``, so a consumer repo with a clean tree gets the strong
guarantee without this repo having to reconcile its corpus first.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_SCHEMAS = Path(__file__).resolve().parent.parent / "schemas"

#: Tier default per kind: ``kind -> (schema file, $ref into it or None, tier)``.
#: The enforce set is measured, not asserted — every kind listed as ``enforce``
#: validates 100% of its in-repo artifacts (wagon 41/41, train 21/21,
#: interlocking 8/8). ``acceptance`` was already enforced at author time by
#: ``create_acceptance``; listing it here moves that same check one stage
#: earlier, to where the block is actually written.
SPEC_SCHEMAS: dict[str, tuple[str, str | None, str]] = {
    "wagon": ("wagon.schema.json", None, "enforce"),
    "train": ("train.schema.json", None, "enforce"),
    "interlocking": ("train-interlocking.schema.json", None, "enforce"),
    "acceptance": (
        "acceptance.schema.json", "#/definitions/embedded_acceptance", "enforce",
    ),
    "feature": ("feature.schema.json", None, "advise"),
    "wmbt": ("wmbt.schema.json", None, "advise"),
}

#: Kinds that name a reasoning move in the dialogue, not an artifact to author.
#: ``planner.decomposition.keep-pivot-kill`` names them as candidate
#: granularities and says an artifact is written "only after a final-granularity
#: keep" — so keeping one is a recorded decision that authors nothing.
REASONING_KINDS = frozenset({"main-job", "heuristic", "analog"})

#: Kinds that resolve to an ``atdd author`` writer in ``build_author_fn``.
AUTHORABLE_KINDS = frozenset(
    {"wagon", "feature", "wmbt", "train", "interlocking", "contract", "acceptance"}
)

KNOWN_KINDS = REASONING_KINDS | AUTHORABLE_KINDS

# Keywords that assert COMPLETENESS (is everything here yet?) rather than
# WELL-FORMEDNESS (is what IS here shaped right?). Dropped for the Compose pass,
# restored for Ratify. See the module docstring.
_COMPLETENESS_KEYWORDS = frozenset(
    {"required", "minItems", "minLength", "minProperties"}
)


def _wellformedness_only(node):
    """``node`` with every completeness keyword stripped, recursively."""
    if isinstance(node, list):
        return [_wellformedness_only(v) for v in node]
    if not isinstance(node, dict):
        return node
    return {
        key: _wellformedness_only(value)
        for key, value in node.items()
        if key not in _COMPLETENESS_KEYWORDS
    }


@lru_cache(maxsize=None)
def _validator(name: str, ref: str | None, complete: bool):
    """A Draft7 validator for ``name``, with sibling schemas resolvable.

    The planner schemas ``$ref`` each other by bare filename
    (``acceptance.schema.json#/definitions/embedded_acceptance``), which no
    default resolver can retrieve — so every sibling is registered by name.
    """
    import jsonschema
    from referencing import Registry, Resource
    from referencing.jsonschema import DRAFT7

    def _load(path: Path) -> dict:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if complete else _wellformedness_only(doc)

    registry = Registry().with_resources(
        [
            (path.name, Resource(contents=_load(path), specification=DRAFT7))
            for path in _SCHEMAS.glob("*.schema.json")
        ]
    )
    schema = _load(_SCHEMAS / name)
    if ref:
        schema = {**schema, "$ref": ref}
    return jsonschema.Draft7Validator(schema, registry=registry)


def project_for_schema(kind: str, spec: dict) -> dict:
    """The document the ``atdd author`` writer would WRITE for ``spec``.

    Validating the raw spec would be dishonest twice over: a writer DROPS
    input-only keys (``wagon_slug``, ``code``) that ``additionalProperties:
    false`` would reject, and it SYNTHESISES required ones (``urn``, a defaulted
    ``to: external``) whose absence is not the operator's error. Projecting first
    means Compose and Author hold the same document to the same schema.

    The projections mirror ``create_wagon`` / ``create_wmbt`` / ``create_acceptance``.
    ``train`` is deliberately NOT mirrored: ``_build_train_doc`` is being
    reworked under #1915 and a re-author now merges with what is on disk, so a
    copy here would drift. ``dict(spec)`` is the honest approximation — it costs
    only that a train spec is checked as written rather than as merged.
    """
    if kind == "wagon":
        doc = {
            key: value
            for key, value in spec.items()
            if key not in ("produce", "consume", "wmbt")
        }
        doc["produce"] = [
            {
                "name": entry.get("name"),
                "contract": entry.get("contract"),
                "telemetry": entry.get("telemetry"),
                "to": entry.get("to", "external"),
            }
            for entry in spec.get("produce", [])
            if isinstance(entry, dict)
        ]
        doc["consume"] = spec.get("consume", [])
        doc["wmbt"] = spec.get("wmbt", {"total": 0})
        return doc
    if kind == "wmbt":
        doc = {"urn": f"wmbt:{spec.get('wagon_slug', '')}:{spec.get('code', '')}"}
        for key in (
            "step", "direction", "dimension", "object_of_control",
            "context_clarifier", "lens", "statement",
        ):
            if key in spec:
                doc[key] = spec[key]
        if spec.get("acceptances"):
            doc["acceptances"] = list(spec["acceptances"])
        return doc
    if kind == "acceptance":
        # `create_acceptance(spec["wmbt_urn"], spec["block"])` — the block is the
        # document; the urn addresses the file it is appended to.
        block = spec.get("block")
        return dict(block) if isinstance(block, dict) else {}
    return dict(spec)


def tier_for(kind: str, config: dict | None = None) -> str:
    """The tier in force for ``kind`` — the repo's ``.atdd/config.yaml`` may
    promote an advisory kind to ``enforce`` (or demote an enforced one)."""
    default = SPEC_SCHEMAS[kind][2]
    block = ((config or {}).get("plan") or {}).get("spec_validation") or {}
    if kind in (block.get("enforce") or []):
        return "enforce"
    if kind in (block.get("advise") or []):
        return "advise"
    return default


def check_unit_spec(
    kind: str,
    spec: dict,
    *,
    config: dict | None = None,
    stage: str = "compose",
) -> tuple[str, list[str]]:
    """Return ``(tier, findings)`` for one unit spec.

    ``tier`` is ``enforce``, ``advise`` or ``skip`` (a kind with no schema —
    ``contract`` and the reasoning kinds). ``findings`` are human-readable
    ``field: message`` strings, empty when the projected document satisfies the
    schema. ``stage`` is ``compose`` (well-formedness) or ``ratify`` (+
    completeness) — see the module docstring.
    """
    if kind not in SPEC_SCHEMAS:
        return "skip", []
    name, ref, _ = SPEC_SCHEMAS[kind]
    document = project_for_schema(kind, spec)
    errors = sorted(
        _validator(name, ref, stage == "ratify").iter_errors(document), key=str
    )
    findings = [
        f"{'.'.join(str(part) for part in error.absolute_path) or '<root>'}: "
        f"{error.message}"
        for error in errors
    ]
    return tier_for(kind, config), findings
