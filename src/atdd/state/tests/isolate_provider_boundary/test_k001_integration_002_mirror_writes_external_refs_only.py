# URN: test:isolate-provider-boundary:validate-extension-integration:K001-INTEGRATION-002-mirror-writes-external-refs-only
# Acceptance: acc:isolate-provider-boundary:K001-INTEGRATION-002-mirror-writes-external-refs-only
# WMBT: wmbt:isolate-provider-boundary:K001
# Phase: GREEN
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: A successful mirror() over a real committed projection changes ONLY external_refs.* — every other field is byte-identical, no phase/state/slug/train/wmbts is written — the applied refs are bot-namespaced, and a provider that tries to write a lifecycle field is refused with the whole write abandoned. Refs #1400.
"""A successful mirror writes external_refs and nothing else (K001-INTEGRATION-002).

wagon: isolate-provider-boundary | feature: validate-extension-integration | phase: GREEN
WMBT: wmbt:isolate-provider-boundary:K001

Not "the mirror does not currently write a lifecycle field" — that it *cannot*. The assertion is
made positively (external_refs is what changed) and negatively (every single other field, one by
one, is byte-identical to what it was), so a future provider that learns to set ``phase`` fails
here rather than in a projection somebody trusts.

The last case is the one an ownership table without a seam would miss. A provider that returns a
perfectly well-formed, bot-namespaced ref, and *also* a record aimed at a lifecycle field, does not
get the good half applied and the bad half refused. The whole write is abandoned. A mirror that can
half-land is a mirror that can corrupt.
"""
from __future__ import annotations

import pytest
import yaml

from atdd.state import ownership, provider_seam
from atdd.state.provider_seam import ProviderBoundaryError

from ._helpers_k001 import bare_repo_with_object
from ._seam import Ref, StubProvider, factory


def test_k001_integration_002_mirror_writes_external_refs_only(tmp_path) -> None:
    """Only external_refs.* changes; every lifecycle field is byte-identical afterwards."""
    repo, uid, _base = bare_repo_with_object(tmp_path)
    path = repo / ".atdd" / "state" / "projection" / f"{uid}.yaml"
    before = yaml.safe_load(path.read_text(encoding="utf-8"))

    provider_seam.register_provider("demo", factory(StubProvider(name="demo")))
    documents = {uid: before}

    result = provider_seam.mirror_all(provider_seam.discover_providers(), documents)
    after = provider_seam.apply_updates(documents, result.updates)[uid]

    # The refs landed, and they are bot-namespaced.
    assert result.updates
    assert all(update.namespace == "bot:demo" for update in result.updates)
    assert all(update.authoritative is False for update in result.updates)
    assert after["external_refs"] == {"demo": {"issue_number": "1400"}}

    # And EVERY other field is exactly what it was. Field by field, not "the document looks fine".
    for name in set(before) | set(after):
        if name == "external_refs":
            continue
        assert before.get(name) == after.get(name), f"the mirror wrote {name!r}, which is not its"

    # Said once more against the ownership table, so the claim is anchored to the policy rather
    # than to this test's idea of which fields are lifecycle fields (spec §7.1).
    policy = ownership.default_policy()
    for name, owner in policy.fields.items():
        if owner.writer != ownership.WRITER_EXTENSION_BOT:
            assert before.get(name) == after.get(name), (
                f"{name!r} is owned by {owner.writer}, and the mirror wrote it"
            )


def test_k001_integration_002_a_provider_reaching_for_a_lifecycle_field_is_refused(tmp_path) -> None:
    """The good ref and the bad one arrive together. Neither is applied."""
    repo, uid, _base = bare_repo_with_object(tmp_path)
    path = repo / ".atdd" / "state" / "projection" / f"{uid}.yaml"
    before = yaml.safe_load(path.read_text(encoding="utf-8"))
    original = dict(before)

    good = Ref(uid=uid, provider="demo", namespace="bot:demo",
               ref_kind="issue_number", ref_value="1400")
    # A ref that is not bot-namespaced: the provider claiming to write as something other than a bot.
    overreaching = Ref(uid=uid, provider="demo", namespace="core-lifecycle",
                       ref_kind="phase", ref_value="GREEN")

    with pytest.raises(ProviderBoundaryError) as refusal:
        provider_seam.apply_updates({uid: before}, [good, overreaching])

    assert refusal.value.rule == provider_seam.RULE_BOT_NAMESPACE

    # Nothing at all was applied — not even the well-formed record that arrived first.
    assert before == original
    assert before.get("external_refs") in (None, {})
    assert before.get("phase") != "GREEN"


def test_k001_integration_002_the_mirror_cannot_invent_an_object(tmp_path) -> None:
    """A ref naming an object the projection does not carry is refused — the mirror reports, it does not create."""
    repo, uid, _base = bare_repo_with_object(tmp_path)
    before = yaml.safe_load(
        (repo / ".atdd" / "state" / "projection" / f"{uid}.yaml").read_text(encoding="utf-8"))

    ghost = Ref(uid="wi_01HF7YAT00M78607F0000000Z9", provider="demo", namespace="bot:demo",
                ref_kind="issue_number", ref_value="9999")

    with pytest.raises(ProviderBoundaryError) as refusal:
        provider_seam.apply_updates({uid: before}, [ghost])

    assert "not in the projection" in str(refusal.value)
    assert "never creates one" in str(refusal.value)
