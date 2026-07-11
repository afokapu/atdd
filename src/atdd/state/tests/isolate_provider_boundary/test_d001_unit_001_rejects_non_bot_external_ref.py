# URN: test:isolate-provider-boundary:define-provider-interface:D001-UNIT-001-rejects-non-bot-external-ref
# Acceptance: acc:isolate-provider-boundary:D001-UNIT-001-rejects-non-bot-external-ref
# WMBT: wmbt:isolate-provider-boundary:D001
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: A mirror() record outside the bot namespace, or one claiming to be authoritative, is refused at the seam and never reaches external_refs; a detect_drift() record claiming authoritative lifecycle state is refused as an alarm-only contract violation; and no projection field outside external_refs.* is written by any of it. Refs #1400.
"""The seam refuses what it may not carry, and writes nothing when it does (D001-UNIT-001).

wagon: isolate-provider-boundary | feature: define-provider-interface | phase: RED
WMBT: wmbt:isolate-provider-boundary:D001

Two stubs, two ways of overstepping: one returns an ``ExternalRefUpdate`` outside the bot namespace
(and one that says outright that it is authoritative), and one returns a drift record that claims
lifecycle state. Neither is stopped by good manners; both are refused by the seam, which is the
only place a refusal is worth anything — a provider lives in someone else's repository and cannot
be trusted to police itself.

The final assertion is the quiet one: *nothing was written*. A seam that refused the record but had
already applied half of it would be a seam that loses.
"""
from __future__ import annotations

import pytest

from atdd.state import provider_seam
from atdd.state.provider_seam import ProviderBoundaryError

from ._seam import UID_X, Alarm, Ref, document, projection


def test_d001_unit_001_rejects_non_bot_external_ref() -> None:
    """A non-bot ref, an authoritative ref, and an authoritative alarm are each refused."""
    before = projection(document(external_refs={"github": {"issue_number": "1400"}}))

    # A ref outside the bot namespace. `mirror()` may return only bot-namespaced records.
    human = Ref(uid=UID_X, provider="github", namespace="human",
                ref_kind="issue_number", ref_value="1401")
    with pytest.raises(ProviderBoundaryError) as refusal:
        provider_seam.apply_updates(before, [human])
    assert refusal.value.rule == provider_seam.RULE_BOT_NAMESPACE
    assert "human" in str(refusal.value)
    assert "§8.2" in str(refusal.value)

    # A ref that says it is authoritative. It is refused for SAYING so — the claim is not quietly
    # dropped, because a provider that believes it is a source of truth is a bug worth surfacing.
    authoritative = Ref(uid=UID_X, provider="github", namespace="bot:github",
                        ref_kind="issue_number", ref_value="1402", authoritative=True)
    with pytest.raises(ProviderBoundaryError) as claim:
        provider_seam.apply_updates(before, [authoritative])
    assert claim.value.rule == provider_seam.RULE_NON_AUTHORITATIVE
    assert "I7" in str(claim.value)

    # A drift record claiming authoritative lifecycle state. detect_drift() is alarm-only.
    with pytest.raises(ProviderBoundaryError) as flagged:
        provider_seam.validate_alarm(
            Alarm(uid=UID_X, provider="github", kind="phase-drift", authoritative=True))
    assert flagged.value.rule == provider_seam.RULE_ALARM_ONLY

    # ...and the subtler form: not "I am authoritative", but a claim ON a lifecycle field.
    with pytest.raises(ProviderBoundaryError) as claims_phase:
        provider_seam.validate_alarm(
            Alarm(uid=UID_X, provider="github", kind="phase-drift", claims={"phase": "GREEN"}))
    assert claims_phase.value.rule == provider_seam.RULE_ALARM_ONLY
    assert "phase" in str(claims_phase.value)

    # A provider may not forge another provider's refs either — the ownership table knows only
    # that "the bot" owns external_refs, so cross-provider forgery would slip past it.
    with pytest.raises(ProviderBoundaryError) as forged:
        provider_seam.validate_update(
            Ref(uid=UID_X, provider="gitlab", namespace="bot:gitlab",
                ref_kind="issue_number", ref_value="7"),
            provider="github")
    assert forged.value.rule == provider_seam.RULE_PROVIDER_IDENTITY

    # Nothing was applied. Not the refused record, and not any part of it.
    assert before == projection(document(external_refs={"github": {"issue_number": "1400"}}))


def test_d001_unit_001_refused_records_never_reach_external_refs() -> None:
    """A refused mirror leaves the projection byte-for-byte as it was — no partial write."""
    before = projection(document(external_refs={"github": {"issue_number": "1400"}}))
    good = Ref(uid=UID_X, provider="github", namespace="bot:github",
               ref_kind="url", ref_value="https://example.invalid/1400")
    bad = Ref(uid=UID_X, provider="github", namespace="nope",
              ref_kind="issue_number", ref_value="1401")

    # The good record comes FIRST, so a seam that applied as it went would have written it before
    # meeting the bad one. Nothing may survive the refusal.
    with pytest.raises(ProviderBoundaryError):
        provider_seam.apply_updates(before, [good, bad])

    assert before[UID_X]["external_refs"] == {"github": {"issue_number": "1400"}}
    assert "url" not in before[UID_X]["external_refs"]["github"]
