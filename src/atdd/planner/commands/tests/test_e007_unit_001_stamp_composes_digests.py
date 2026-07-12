# URN: test:author-plan-substrate:author-interlocking:E007-UNIT-001-stamp-composes-digests
# Acceptance: acc:author-plan-substrate:E007-UNIT-001-stamp-composes-digests
# WMBT: wmbt:author-plan-substrate:E007
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""E007-UNIT-001 — stamp_interlocking_digests derives digests by composing the
#1248 digest math, byte-matching what the #1249 gate recomputes.

RED: stamp_interlocking_digests does not exist yet.
"""
from __future__ import annotations

import yaml

from atdd.planner.interlocking import (
    build_coverage,
    load_interlocking,
    normalized_interlocking_digest,
    project_route_to_train_sequence,
    route_projection_digest,
    stamp_interlocking_digests,
)
from atdd.planner.interlocking import sanity
from atdd.planner.interlocking.tests._fixtures import interlocking_doc, write_tree


def test_stamp_byte_matches_gate_recompute(tmp_path):
    # write_tree materializes the two route trains + a placeholder interlocking.
    il_path = write_tree(tmp_path)
    doc = interlocking_doc()  # placeholder digests

    stamped = stamp_interlocking_digests(doc, tmp_path)

    # 1) Every route digest is now derived (no placeholder left) AND equals an
    #    independent compose of project_route_to_train_sequence + route_projection_digest.
    model = load_interlocking(il_path)  # loaded only to project route steps from disk
    for route_dict in stamped["routes"]:
        expected = route_projection_digest(
            project_route_to_train_sequence(model, route_dict["route_id"]),
            tuple(route_dict["projection"].get("fields")
                  or ("step", "intent", "from", "to", "artifact")),
        )
        assert route_dict["projection"]["expected_sequence_digest"] == expected
        assert route_dict["projection"]["expected_sequence_digest"] != "PLACEHOLDER"

    # 2) content_digest is the normalized digest of the route-stamped doc.
    assert stamped["source"]["content_digest"] == normalized_interlocking_digest(stamped)
    assert stamped["source"]["content_digest"] != "PLACEHOLDER"

    # 3) The gate's own recompute agrees: writing the stamped doc and running the
    #    #1249 projection-equivalence sanity rule yields ZERO rows.
    il_path.write_text(yaml.safe_dump(stamped, sort_keys=False), encoding="utf-8")
    reloaded = load_interlocking(il_path)
    assert sanity.projection_equivalence_violations(reloaded, tmp_path) == []
    for row in build_coverage(reloaded)["routes"]:
        assert row["projection_matches"] is True
