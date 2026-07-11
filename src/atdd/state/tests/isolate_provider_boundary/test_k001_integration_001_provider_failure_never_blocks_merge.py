# URN: test:isolate-provider-boundary:validate-extension-integration:K001-INTEGRATION-001-provider-failure-never-blocks-merge
# Acceptance: acc:isolate-provider-boundary:K001-INTEGRATION-001-provider-failure-never-blocks-merge
# WMBT: wmbt:isolate-provider-boundary:K001
# Phase: RED
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: With a registered provider whose mirror() raises, over a branch whose projection is otherwise valid: the merge-authority run's seven checks all pass and the merge proceeds; the provider failure surfaces as a DriftAlarm rather than a gate failure; the projection is byte-for-byte unchanged by the failed mirror; and the mirror CLI itself exits 0. Refs #1400.
"""A broken mirror is an alarm, not a gate (K001-INTEGRATION-001).

wagon: isolate-provider-boundary | feature: validate-extension-integration | phase: RED
WMBT: wmbt:isolate-provider-boundary:K001

If a failing GitHub mirror could return non-zero into a CI job, then GitHub being down would block
a merge — and core would have grown, through the back door, exactly the dependency §8.1 exists to
forbid. So the mirror raising is caught, recorded as a :class:`DriftAlarm`, and dropped on the
floor as far as merge authority is concerned.

That is easy to state and easy to get wrong in the one direction that matters, so it is checked
against the *real* merge-authority run — the same seven checks that decide whether a branch may
land — with the broken provider registered, on a real repo. The run passes. The projection is
untouched. And ``atdd state mirror`` exits **0**, which looks like a bug until you remember what
the alternative costs.
"""
from __future__ import annotations

import yaml

from atdd.state import merge_authority, provider_seam
from atdd.state.projection import canonical_bytes

from ._helpers_k001 import bare_repo_with_object
from ._seam import UID_X, FailingProvider, StubProvider, document, factory, projection


def test_k001_integration_001_provider_failure_never_blocks_merge(tmp_path) -> None:
    """The merge-authority run passes with a provider that raises; the failure is an alarm."""
    repo, uid, base = bare_repo_with_object(tmp_path)
    before = (repo / ".atdd" / "state" / "projection" / f"{uid}.yaml").read_bytes()

    broken = FailingProvider(name="broken")
    provider_seam.register_provider("broken", factory(broken))

    # The gate that decides whether this branch may land, run for real, with the broken provider
    # registered in the very same process.
    result = merge_authority.run_repo(repo, base_ref=base, actor="core-lifecycle")

    assert result.ok, result.render()
    assert result.failed == []
    assert len(result.results) == 7, "the full required-check set ran"

    # The gate never even asked the provider anything — it cannot.
    assert broken.invoked == 0

    # The mirror path, run separately, DOES ask it. And the provider explodes.
    documents = {uid: yaml.safe_load(before.decode("utf-8"))}
    mirrored = provider_seam.mirror_all(provider_seam.discover_providers(), documents)

    assert broken.invoked == 1, "the mirror really did call the provider"
    assert not mirrored.ok
    assert mirrored.failed == ["broken"]

    # The failure surfaced as an ALARM, carrying what went wrong — not as an exception, and not as
    # a gate verdict. Its drift channel is not then asked for a second opinion: a provider that
    # could not mirror has already said everything it is able to say.
    assert [alarm.kind for alarm in mirrored.alarms] == ["mirror-failed"]
    assert all("503" in alarm.detail for alarm in mirrored.alarms)
    assert mirrored.updates == []

    # The projection is unchanged by the failed mirror attempt.
    applied = provider_seam.apply_updates(documents, mirrored.updates)
    assert canonical_bytes(applied[uid]) == before

    # And the gate still passes, after the mirror failed. Merge authority never knew.
    again = merge_authority.run_repo(repo, base_ref=base, actor="core-lifecycle")
    assert again.ok, again.render()


def test_k001_integration_001_one_broken_provider_does_not_stop_a_working_one(tmp_path) -> None:
    """A failing extension degrades itself, not the mirror. The healthy provider still mirrors."""
    provider_seam.register_provider("broken", factory(FailingProvider(name="broken")))
    provider_seam.register_provider("demo", factory(StubProvider(name="demo")))

    documents = projection(document())
    result = provider_seam.mirror_all(provider_seam.discover_providers(), documents)

    assert result.failed == ["broken"]
    assert [update.provider for update in result.updates] == ["demo"], (
        "the working provider mirrored, though the one before it in name order had just blown up"
    )
    assert any(alarm.provider == "broken" for alarm in result.alarms)

    applied = provider_seam.apply_updates(documents, result.updates)
    assert applied[UID_X]["external_refs"] == {"demo": {"issue_number": "1400"}}
