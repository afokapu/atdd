# URN: test:govern-lifecycle:bind-issue-feature:Y006-INTEGRATION-001-backfill-skip-guard-requires-resolvable
# Acceptance: acc:govern-lifecycle:Y006-INTEGRATION-001-backfill-populates-null-bindings
# WMBT: wmbt:govern-lifecycle:Y006
# Phase: RED
# Layer: application
# Runtime: python
# Assertion: behavioral
# Purpose: The backfill's "already bound" skip means RESOLVABLE, not merely truthy, so a stored value that resolves to nothing is repaired from the body where it can be and reported where it cannot — instead of being protected from repair by the guard meant to be conservative.
"""#1689 — closing the door, not just mopping the floor.

THE DEFECT. The skip guard read ``if data.get("feature"): continue``. Truthy, not
resolvable. So a work item whose stored feature is the string ``"TBD"`` counted
as bound: the backfill stepped over it, and it appeared in NEITHER the written
list nor the unresolved list. It vanished from the report entirely.

Measured against the live store on 2026-08-03, of 381 work items carrying a
stored feature:

    225  resolve against plan/
    152  are literally 'TBD'  ─┐
      4  name a feature plan/  ├─ 156 rows the report never mentioned
         does not contain     ─┘

An operator could run the backfill to completion, read "wrote 0", and conclude
the store was clean.

WHY IT BELONGS IN THIS ISSUE RATHER THAN A FOLLOW-UP. It repairs zero rows today
— every one of those 156 has a body declaring the same garbage, so there is
nothing better to write. That is exactly why it ships here: the value is
truthy-but-unresolvable, gets stored, and then fails to resolve downstream, which
is the bug #1689 exists to remove re-entering through the write path #1689 is
fixing. Repairing the data while leaving the guard that hid it is a fix with its
own door propped open.

WHAT DID NOT CHANGE. A binding that RESOLVES is still never overwritten. The
backfill still refuses to guess: a broken stored value is only replaced when the
body declares a URN that resolves, and is otherwise reported, never cleared and
never invented.
"""
from __future__ import annotations

import pytest

from ._bind_issue_feature_helpers import (
    FEATURE_URN,
    TRAIN_URN_IN_FEATURE_SLOT,
    control_root,
    open_store,
    read_issue_data,
    seed_issue,
    write_plan_tree,
)

pytestmark = [pytest.mark.platform]

# A stored value that is truthy and resolves to nothing — the live shape.
PLACEHOLDER = "TBD"
ABSENT_FEATURE_URN = "feature:govern-lifecycle:no-such-feature-exists"

REPAIRABLE = 94001    # stored 'TBD', body declares a URN that resolves
UNREPAIRABLE = 94002  # stored 'TBD', body declares 'TBD' too
STALE_URN = 94003     # stored a well-formed URN naming no file in plan/
HEALTHY = 94004       # stored a binding that resolves — must be left alone
NULL_BINDING = 94005  # no stored feature at all — the original #1689 population


def _backfill():
    from atdd.coach.commands.issue_feature_binding import backfill_feature_bindings

    return backfill_feature_bindings


@pytest.fixture()
def seeded(tmp_path):
    root = control_root(tmp_path)
    write_plan_tree(root)
    store = open_store(root)

    seed_issue(store, slug="repairable", issue_number=REPAIRABLE,
               feature=PLACEHOLDER, body=f"| Feature | `{FEATURE_URN}` |")
    seed_issue(store, slug="unrepairable", issue_number=UNREPAIRABLE,
               feature=PLACEHOLDER, body=f"| Feature | `{PLACEHOLDER}` |")
    seed_issue(store, slug="stale-urn", issue_number=STALE_URN,
               feature=ABSENT_FEATURE_URN, body=f"| Feature | `{ABSENT_FEATURE_URN}` |")
    seed_issue(store, slug="healthy", issue_number=HEALTHY,
               feature=FEATURE_URN, body=f"| Feature | `{FEATURE_URN}` |")
    seed_issue(store, slug="null-binding", issue_number=NULL_BINDING,
               feature=None, body=f"| Feature | `{FEATURE_URN}` |")
    return root, store


# ---------------------------------------------------------------------------
# 1. Truthy is not bound
# ---------------------------------------------------------------------------
class TestABrokenBindingIsNotTreatedAsBound:
    def test_a_placeholder_is_repaired_from_the_body(self, seeded):
        """'TBD' is not a binding; it is the absence of one wearing a value."""
        root, store = seeded

        report = _backfill()(control_root=root)

        assert read_issue_data(store, REPAIRABLE)["feature"] == FEATURE_URN, (
            "a stored 'TBD' was protected from repair by the skip guard — the "
            "defect the guard was supposed to prevent, preserved by the guard"
        )
        assert REPAIRABLE in report.written

    def test_a_well_formed_but_stale_urn_is_also_not_a_binding(self, seeded):
        """Resolution, not grammar, decides. A URN naming no file leads nowhere."""
        root, store = seeded

        report = _backfill()(control_root=root)

        assert STALE_URN in report.unrepairable, (
            "a feature URN that resolves to nothing in plan/ was counted as a "
            "binding because it merely looked like one"
        )
        assert read_issue_data(store, STALE_URN)["feature"] == ABSENT_FEATURE_URN, (
            "a stored binding was cleared; the backfill reports, it does not erase"
        )


# ---------------------------------------------------------------------------
# 2. The rows that used to vanish are now named
# ---------------------------------------------------------------------------
class TestTheReportNamesEveryRowItPassedOver:
    def test_an_unrepairable_row_is_reported_not_silently_skipped(self, seeded):
        """The 156-row blind spot: reported in neither list, so invisible."""
        root, store = seeded

        report = _backfill()(control_root=root)

        assert UNREPAIRABLE in report.unrepairable, (
            "a work item carrying an unresolvable binding appeared in no list; "
            "an operator reading this report would conclude the store was clean"
        )
        assert UNREPAIRABLE not in report.written
        assert UNREPAIRABLE not in report.unresolved, (
            "a broken binding was conflated with having no binding — the two "
            "need different remedies and must read differently"
        )

    def test_a_null_binding_is_still_reported_as_unresolved_not_unrepairable(self, seeded):
        """The two outcomes stay distinct in both directions."""
        root, store = seeded
        # NULL_BINDING's body resolves, so it is written rather than reported;
        # seed a second null row whose body declares nothing to observe the
        # unresolved path itself.
        seed_issue(store, slug="silent", issue_number=94006, feature=None,
                   body="no metadata table here")

        report = _backfill()(control_root=root)

        assert 94006 in report.unresolved
        assert 94006 not in report.unrepairable, (
            "an issue with no binding at all was labelled a broken binding"
        )

    def test_every_issue_lands_in_exactly_one_bucket(self, seeded):
        """No row may fall through the report unaccounted for."""
        root, _store = seeded

        report = _backfill()(control_root=root)

        buckets = [set(report.written), set(report.unresolved), set(report.unrepairable)]
        seen = set().union(*buckets)
        assert seen == {REPAIRABLE, UNREPAIRABLE, STALE_URN, NULL_BINDING}, (
            f"accounted for {sorted(seen)}; HEALTHY is correctly absent (it was "
            "skipped as already-resolving) and every other row must appear"
        )
        assert sum(len(b) for b in buckets) == len(seen), "a row appears in two buckets"


# ---------------------------------------------------------------------------
# 3. What did NOT change — the conservative half of the contract
# ---------------------------------------------------------------------------
class TestAResolvableBindingIsStillNeverOverwritten:
    def test_a_healthy_binding_is_left_alone_and_not_reported(self, seeded):
        root, store = seeded

        report = _backfill()(control_root=root)

        assert read_issue_data(store, HEALTHY)["feature"] == FEATURE_URN
        assert HEALTHY not in report.written
        assert HEALTHY not in report.unrepairable

    def test_the_backfill_still_refuses_to_write_a_train_urn_over_a_placeholder(self, tmp_path):
        """Repairing a broken binding must not relax the anti-guess rule.

        A row whose stored value is garbage AND whose body carries the #1626
        train-URN drift is the case where a looser guard would do real damage:
        it would replace one wrong value with another and call it a repair.
        """
        root = control_root(tmp_path)
        write_plan_tree(root)
        store = open_store(root)
        seed_issue(store, slug="drift", issue_number=94007, feature=PLACEHOLDER,
                   body=f"| Feature | `{TRAIN_URN_IN_FEATURE_SLOT}` |")

        report = _backfill()(control_root=root)

        assert read_issue_data(store, 94007)["feature"] == PLACEHOLDER, (
            "a train identity was written over a placeholder — the backfill "
            "manufactured a binding out of the drift it was built to find"
        )
        assert 94007 in report.unrepairable

    def test_a_second_run_writes_nothing_further(self, seeded):
        """Repaired rows now resolve, so idempotence survives the looser guard."""
        root, _store = seeded
        fn = _backfill()

        first = fn(control_root=root)
        second = fn(control_root=root)

        assert first.written, "the fixture must exercise the write path"
        assert second.written == (), (
            "the second run rewrote rows the first had already repaired"
        )
        assert set(first.unrepairable) == set(second.unrepairable)

    def test_dry_run_repairs_nothing(self, seeded):
        root, store = seeded

        report = _backfill()(control_root=root, dry_run=True)

        assert REPAIRABLE in report.written, "the preview must still name the row"
        assert read_issue_data(store, REPAIRABLE)["feature"] == PLACEHOLDER, (
            "--dry-run repaired a broken binding; a preview that writes is worse "
            "than no preview, because it is trusted"
        )
