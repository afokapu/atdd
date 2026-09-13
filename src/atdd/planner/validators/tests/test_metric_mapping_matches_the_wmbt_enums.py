"""#1959 — the dimension->metric table and ``wmbt.schema.json`` must agree.

Two declarations describe the same pair space, and they had drifted:

* ``wmbt.schema.json`` — ``dimension`` (6 values) and ``direction`` (4 values)
  own the vocabulary a WMBT may legally carry. 24 pairs are legal.
* ``planner.criteria.metric-mapping``, term ``dimension_metric`` — the lookup
  keyed on exactly those two enums. It defined 10 pairs.

The table spelled three of its downward entries ``decrease`` while the corpus
writes ``minimize`` — a different word for the same legal intent — and spelled
one dimension ``quantity / amount`` where the enum says ``quantity``. Measured
over the 472 authored WMBTs, 104 fell through the table to nothing, 102 of them
purely on the ``decrease``/``minimize`` spelling. Nothing noticed, because a
partial table with no coverage check is indistinguishable from a complete one
until someone counts.

This is the ``test_acceptance_schema_urn_pattern_matches_the_grammar`` pattern
applied to a lookup table instead of a regex: two declarations that must agree
are pinned to each other rather than hoped about. The table is required to be
TOTAL over the enum product — a pair with no default metric carries the
``unmapped`` sentinel and states its reason, so a reader can tell a deliberate
omission from a missing row.

Nothing reads this table at runtime (#1959 Out of Scope: whether it should be
bound is filed separately). These tests are the only thing holding the two
declarations together.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml

from atdd.coach.utils.repo import find_repo_root

pytestmark = [pytest.mark.planner]


_PLANNER = Path(__file__).resolve().parents[2]
_WMBT_SCHEMA = _PLANNER / "schemas" / "wmbt.schema.json"
_MAPPING_NODE = (
    _PLANNER / "conventions" / "nodes"
    / "planner.criteria.metric-mapping.convention.yaml"
)

#: The value a dimension+direction pair carries when no default metric is
#: declared for it. Explicit, so omission is a statement rather than a gap.
UNMAPPED = "unmapped"

_METRIC_ID = re.compile(r"^metric:[a-z][a-z0-9_]*$")

#: The 10 pairs the table carried before #1959, at the enum's spelling of the
#: dimension. Reconciliation ADDS vocabulary; it must not silently re-point an
#: entry that already existed.
HISTORICAL_PAIRS = {
    ("time", "minimize"): "metric:latency_p50",
    ("time", "maximize"): "metric:latency_increase",
    ("likelihood", "maximize"): "metric:success_ratio",
    ("likelihood", "minimize"): "metric:error_ratio",
    ("effort", "decrease"): "metric:user_steps",
    ("frequency", "decrease"): "metric:occurrence_rate",
    # authored as `quantity / amount`, which is not the enum's spelling
    ("quantity", "decrease"): "metric:scrap_rate",
    ("quantity", "maximize"): "metric:throughput",
    ("financial value", "minimize"): "metric:cost_per_unit",
    ("financial value", "maximize"): "metric:net_margin",
}


def _schema_enum(prop: str) -> set:
    schema = json.loads(_WMBT_SCHEMA.read_text(encoding="utf-8"))
    return set(schema["properties"][prop]["enum"])


def _terms() -> dict:
    doc = yaml.safe_load(_MAPPING_NODE.read_text(encoding="utf-8")) or {}
    return {
        t["term_id"]: (t.get("values") or {})
        for t in (doc.get("terms") or [])
        if isinstance(t, dict) and t.get("term_id")
    }


def _mapping() -> dict:
    return _terms()["dimension_metric"]


def _authored_wmbts() -> list:
    """Every WMBT on disk in the consumer repo's ``plan/``."""
    plan = find_repo_root() / "plan"
    out = []
    for path in sorted(plan.rglob("*.yaml")):
        try:
            doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(doc, dict) and str(doc.get("urn", "")).startswith("wmbt:"):
            out.append((path, doc))
    return out


# ---------------------------------------------------------------------------
# The table's keys are the schema's enums — both directions, no drift either way
# ---------------------------------------------------------------------------


def test_mapping_dimensions_are_exactly_the_schema_dimension_enum():
    """Not a subset and not a superset: a key the enum cannot produce is dead,
    and an enum value with no key is a silent fall-through."""
    assert set(_mapping()) == _schema_enum("dimension"), (
        "planner.criteria.metric-mapping dimension keys have drifted from "
        "wmbt.schema.json properties.dimension.enum; the schema owns the "
        "vocabulary — key the table at its exact spelling"
    )


@pytest.mark.parametrize("dimension", sorted(_schema_enum("dimension")))
def test_each_dimension_declares_every_legal_direction(dimension):
    """Total over the enum product: 6 dimensions x 4 directions = 24 pairs."""
    directions = _mapping().get(dimension) or {}
    assert set(directions) == _schema_enum("direction"), (
        f"dimension {dimension!r} does not declare every direction in "
        f"wmbt.schema.json properties.direction.enum; a legal WMBT carrying an "
        f"undeclared direction falls through the table with no signal"
    )


def test_every_entry_is_a_metric_id_or_the_unmapped_sentinel():
    bad = {
        (dim, direction): value
        for dim, directions in _mapping().items()
        for direction, value in directions.items()
        if value != UNMAPPED and not _METRIC_ID.match(str(value))
    }
    assert not bad, f"entries are neither a metric id nor {UNMAPPED!r}: {bad}"


# ---------------------------------------------------------------------------
# minimize/decrease and maximize/increase are one intent in two words
# ---------------------------------------------------------------------------


def test_direction_synonyms_partition_the_direction_enum():
    """The grouping is declared on the node, not invented by this test."""
    groups = _terms().get("direction_synonyms") or {}
    assert groups, (
        "planner.criteria.metric-mapping declares no direction_synonyms term; "
        "without it nothing says minimize and decrease are the same intent"
    )
    spellings = [d for group in groups.values() for d in group]
    assert len(spellings) == len(set(spellings)), (
        f"a direction is claimed by two synonym groups: {groups}"
    )
    assert set(spellings) == _schema_enum("direction"), (
        f"direction_synonyms does not partition the direction enum: {groups}"
    )


def test_synonymous_directions_map_to_the_same_metric():
    """#1959's bug in one assertion: `quantity/decrease` resolved and
    `quantity/minimize` did not, for 94 WMBTs, on a spelling alone."""
    mapping = _mapping()
    disagreements = {}
    for label, group in (_terms().get("direction_synonyms") or {}).items():
        for dimension, directions in mapping.items():
            resolved = {directions.get(d) for d in group}
            if len(resolved) > 1:
                disagreements[(dimension, label)] = {
                    d: directions.get(d) for d in group
                }
    assert not disagreements, (
        f"synonymous directions resolve differently: {disagreements}"
    )


# ---------------------------------------------------------------------------
# An omission must say it is one
# ---------------------------------------------------------------------------


def test_every_unmapped_pair_states_why_and_every_stated_reason_is_used():
    """Bijection between sentinel entries and declared rationales, so neither a
    silent `unmapped` nor a rationale for a pair that now maps can survive."""
    sentinels = {
        (dim, direction)
        for dim, directions in _mapping().items()
        for direction, value in directions.items()
        if value == UNMAPPED
    }
    declared = {
        (dim, direction): reason
        for dim, directions in (_terms().get("unmapped_pairs") or {}).items()
        for direction, reason in directions.items()
    }
    assert sentinels == set(declared), (
        f"unmapped entries and declared rationales disagree; "
        f"sentinel-only={sorted(sentinels - set(declared))}, "
        f"rationale-only={sorted(set(declared) - sentinels)}"
    )
    blank = [pair for pair, reason in declared.items() if not str(reason).strip()]
    assert not blank, f"unmapped pairs declared with no reason: {blank}"


# ---------------------------------------------------------------------------
# The historical entries survive the reconciliation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("pair,metric_id", sorted(HISTORICAL_PAIRS.items()))
def test_a_pair_that_already_mapped_still_maps_to_the_same_metric(pair, metric_id):
    dimension, direction = pair
    assert (_mapping().get(dimension) or {}).get(direction) == metric_id, (
        f"{dimension}/{direction} no longer resolves to {metric_id}; #1959 "
        f"widens the table's vocabulary, it does not re-point existing entries"
    )


# ---------------------------------------------------------------------------
# The corpus the issue measured: nothing falls through
# ---------------------------------------------------------------------------


def test_no_authored_wmbt_falls_through_the_mapping():
    """104 of 472 did, before #1959. The table is now total over the enums, so
    the only way to land here again is a WMBT off the enum entirely."""
    wmbts = _authored_wmbts()
    if not wmbts:
        pytest.skip("no authored WMBTs in this checkout's plan/")
    mapping = _mapping()
    fell_through = [
        (str(path), doc.get("dimension"), doc.get("direction"))
        for path, doc in wmbts
        if (mapping.get(doc.get("dimension")) or {}).get(doc.get("direction")) is None
    ]
    assert not fell_through, (
        f"{len(fell_through)} of {len(wmbts)} authored WMBTs carry a "
        f"dimension+direction the table does not resolve: {fell_through[:5]}"
    )
