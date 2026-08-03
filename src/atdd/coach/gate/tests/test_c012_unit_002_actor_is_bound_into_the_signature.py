# URN: test:govern-lifecycle:operator-approval-token-gate:C012-UNIT-002-actor-is-bound-into-the-signature
# Acceptance: acc:govern-lifecycle:C012-UNIT-002-actor-is-bound-into-the-signature
# WMBT: wmbt:govern-lifecycle:C012
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""C012-UNIT-002 — the recorded attribution is covered by the signature.

Reproduced on 2026-08-03 against the pre-fix code::

    minted approved_by : alecfokapu
    verifies           : True
    after editing approved_by -> someone-else-entirely
    still verifies     : True

``canonical_scope`` signs ``issue:FROM:TO`` only, so ``approved_by`` sits outside
the signature and any process can relabel who approved without invalidating the
token. Recording a better value is therefore necessary but not sufficient: the
actor has to enter the signed scope or the improvement is decoration.

This is an AUDIT-HONESTY property, not an anti-tamper one. ``resolve_signing_key``
falls back to a public constant checked into this repo, so anything that can
import the module can re-sign a rewritten token — see the THREAT MODEL in
``approval.py``. What binding closes is the silent edit, and the drift where a
field nothing signs quietly stops describing reality.

The 169 tokens already on disk carry no ``schema_version``, and they must keep
verifying exactly as before; the new binding applies to the new regime only.

RED state: ``TOKEN_SCHEMA_VERSION`` and the ``agent_session`` parameter do not
exist, so the import and the ``build_token`` calls fail.
"""
from __future__ import annotations

import pytest

from atdd.coach.gate.approval import (
    TOKEN_SCHEMA_VERSION,
    build_token,
    canonical_scope,
    describe_attribution,
    sign_approval,
    verify_token,
)

pytestmark = [pytest.mark.platform]

_KEY = "operator-secret-key"
_ISSUE, _FROM, _TO = 1718, "INIT", "PLANNED"
_AT = "2026-08-03T00:00:00Z"
_SESSION = {"provider": "claude", "session_id": "1886c25f-4f38-466c-ae9a-7d94ff0d491f"}


def _human_token() -> dict:
    return build_token(_ISSUE, _FROM, _TO, approved_by="alecfokapu", approved_at=_AT, key=_KEY)


def _agent_token() -> dict:
    return build_token(
        _ISSUE, _FROM, _TO,
        approved_by="agent:claude", approved_at=_AT, agent_session=_SESSION, key=_KEY,
    )


def _pre_fix_token() -> dict:
    """A token shaped exactly like the measured corpus: the union of fields across
    all 169 live tokens is [approved_at, approved_by, from_phase, issue, signature,
    to_phase] and nothing else."""
    return {
        "issue": _ISSUE,
        "from_phase": _FROM,
        "to_phase": _TO,
        "approved_by": "alecfokapu",
        "approved_at": _AT,
        "signature": sign_approval(_ISSUE, _FROM, _TO, _KEY),
    }


def test_a_schema_versioned_token_verifies_and_then_fails_once_its_approver_is_edited():
    token = _human_token()
    # The guard discriminates rather than refusing everything.
    assert verify_token(token, _ISSUE, _FROM, _TO, _KEY) is True

    token["approved_by"] = "someone-else-entirely"
    assert verify_token(token, _ISSUE, _FROM, _TO, _KEY) is False, (
        "the exact 2026-08-03 rewrite still verifies — approved_by is not in the "
        "signed scope"
    )


def test_editing_or_removing_the_recorded_session_invalidates_the_token():
    token = _agent_token()
    assert verify_token(token, _ISSUE, _FROM, _TO, _KEY) is True

    relabelled = dict(token, agent_session={"provider": "claude", "session_id": "not-mine"})
    assert verify_token(relabelled, _ISSUE, _FROM, _TO, _KEY) is False

    stripped = {k: v for k, v in token.items() if k != "agent_session"}
    assert verify_token(stripped, _ISSUE, _FROM, _TO, _KEY) is False, (
        "dropping the session field turned an agent mint back into an unattributed "
        "one while the signature still matched"
    )


def test_the_two_regimes_sign_different_scopes():
    # A human v2 token and a pre-fix token can carry the identical approved_by;
    # they must not carry the identical signature, or the version stamp would be
    # the only thing separating them and it is not signed on the old side.
    assert _human_token()["signature"] != _pre_fix_token()["signature"]
    assert canonical_scope(_ISSUE, _FROM, _TO) != canonical_scope(
        _ISSUE, _FROM, _TO, actor="alecfokapu"
    )


def test_pre_fix_tokens_still_verify_unchanged():
    # 169 of these exist. The new field must not invalidate a single one.
    assert verify_token(_pre_fix_token(), _ISSUE, _FROM, _TO, _KEY) is True


def test_attribution_is_described_by_regime():
    pre_fix = describe_attribution(_pre_fix_token())
    assert "unattributed" in pre_fix.lower(), (
        f"a pre-fix token reads as {pre_fix!r} — a reader still has to trust "
        f"approved_by from a regime that could not attribute"
    )

    agent = describe_attribution(_agent_token())
    assert _SESSION["session_id"] in agent
    assert "unattributed" not in agent.lower()

    human = describe_attribution(_human_token())
    assert "alecfokapu" in human
    assert "unattributed" not in human.lower()
    # A human mint under the new regime is not the same claim as an agent mint,
    # so the two descriptions must not collapse into one another.
    assert human != agent


def test_the_schema_version_is_stamped_on_every_minted_token():
    for token in (_human_token(), _agent_token()):
        assert token["schema_version"] == TOKEN_SCHEMA_VERSION
