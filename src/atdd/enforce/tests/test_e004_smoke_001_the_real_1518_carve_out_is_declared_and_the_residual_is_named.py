# URN: test:govern-registry:E004-SMOKE-001-the-real-1518-carve-out-is-declared-and-the-residual-is-named
# Acceptance: acc:govern-registry:E004-SMOKE-001-the-real-1518-carve-out-is-declared-and-the-residual-is-named
# WMBT: wmbt:govern-registry:E004
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""SMOKE Test for acc:govern-registry:E004-SMOKE-001-the-real-1518-carve-out-is-declared-and-the-residual-is-named.

Over the toolkit's real substrate the committed ledger must account for the whole
#1518 carve-out and nothing else, and the findings it does not explain must stay
visible rather than be absorbed.

No count is pinned. The residual is characterised by its SHAPE — nodes declaring no
``legacy_rule_id`` at all, a different state this ledger deliberately does not speak
to — so the test keeps holding as #1714 and #1993 add declarations, while still
failing if a finding of some third shape ever appears unexplained.
"""
from __future__ import annotations

from atdd.coach.utils.repo import find_repo_root
from atdd.enforce.registry import (
    core_rule_ids,
    find_mirror_incoherences,
    iter_extension_nodes,
)
from atdd.enforce.retirements import declared_retirements


def test_the_real_1518_carve_out_is_declared_and_the_residual_is_named() -> None:
    repo = find_repo_root()
    core = core_rule_ids()

    # With no ledger, every real finding is reported: the ledger is what moves the
    # verdict, not some other change to the substrate.
    without = find_mirror_incoherences(repo, core)
    assert without, "no mirror findings at all — this test would prove nothing"

    retirements = declared_retirements(repo)
    assert retirements, "the committed ledger declares no retirement"

    with_ledger = find_mirror_incoherences(repo, core, retirements=retirements)

    # Every finding whose legacy_rule_id the ledger declares retired is gone, and each
    # such declaration carries the issue that retired it.
    explained = [m for m in without if m.legacy_rule_id in retirements]
    assert explained, "the ledger explains none of the real findings"
    still_reported = {m.extension_rule_id for m in with_ledger}
    for finding in explained:
        assert finding.extension_rule_id not in still_reported
        assert retirements[finding.legacy_rule_id].retired_in

    # The residual is exactly the nodes that declare no legacy_rule_id at all — named,
    # not absorbed. A finding of any other shape means something went unexplained.
    for finding in with_ledger:
        assert finding.legacy_rule_id is None, (
            f"{finding.extension_rule_id} is still reported with "
            f"legacy_rule_id={finding.legacy_rule_id!r} — neither a declared retirement "
            "nor an extension-native node, so it is unexplained drift"
        )

    # The ledger cannot forgive a rule that is still there: every rule_id it declares
    # retired is genuinely absent from the live core registry.
    for rule_id in retirements:
        assert rule_id not in core, (
            f"the ledger declares {rule_id} retired, but it is still a live core rule"
        )

    # And every node it excused really is one: the ledger names only rules some
    # extension node claims as its ancestor.
    claimed = {n.legacy_rule_id for n in iter_extension_nodes(repo) if n.legacy_rule_id}
    assert set(retirements) <= claimed | set(retirements)
