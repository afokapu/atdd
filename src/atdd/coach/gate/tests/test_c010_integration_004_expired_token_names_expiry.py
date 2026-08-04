# URN: test:govern-lifecycle:operator-approval-token-gate:C010-INTEGRATION-004-expired-token-names-expiry
# Acceptance: acc:govern-lifecycle:C010-INTEGRATION-004-expired-token-names-expiry
# WMBT: wmbt:govern-lifecycle:C010
# Phase: GREEN
# Layer: integration
# Assertion: behavioral
"""C010-INTEGRATION-004 — an approval ages out, and the gate SAYS it aged out.

Two properties, and the second is the one that matters.

The first is that expiry is enforced at all. ``verify_token`` has taken a ``now``
since #1525 and the gate consumer never passed one, so an approval signed weeks ago
satisfied it today.

The second is that the refusal is LEGIBLE. Before #1721 the gate had exactly one
sentence for every failed verification — *"does not match this transition or its
signature is invalid (scope/signature mismatch)"* — so an expired approval and a
forged one were indistinguishable to the operator reading the output. Those two
demand opposite responses: re-approve, or stop and find out who is minting tokens.
A gate that cannot say why it refused is the defect this program exists to fix, so
"it fails" is not enough here and is asserted as not enough.

WHY THE SIGNATURE IS STILL INTACT AT THAT POINT, and why that is the point. The
expiry is folded into the signed scope, so an expired token is a perfectly valid
signature over a moment that has passed. The check establishes expiry by ELIMINATION
— the same pure verifier answers True without a clock and False with one — rather
than by inferring it from a broken signature. The last test asserts exactly that,
because a diagnosis that only works when the token is also damaged would be useless
on the one case it exists for.

Deterministic without sleeping: the check takes an explicit ``now``, mirroring
``signing_key`` rather than inventing a second injection style.

RED state: ``approve_command`` passes no ``expires_at=`` and ``approval_check``
passes no ``now=``, so the token carries no expiry, nothing can be past it, and the
message has no expiry vocabulary in it at all.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from atdd.coach.gate.approve_command import run as run_approve
from atdd.coach.gate.approval_binding import APPROVAL_TTL
from atdd.coach.gate.approval_check import ApprovalTokenGateCheck
from atdd.coach.gate.approval_paths import approval_token_path
from atdd.coach.gate.decision import GateVerdict
from atdd.state.smoke_evidence import open_state_store

pytestmark = [pytest.mark.platform]

_ISSUE, _FROM, _TO = 999722, "PLANNED", "RED"
_UID = "token-binds-branch-and-expiry-integration-004"
_BRANCH = "feat/token-binds-branch-and-expiry"
_KEY = "integration-operator-key"


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("ATDD_CONTROL_ROOT", str(tmp_path))
    monkeypatch.setenv("ATDD_APPROVAL_SIGNING_KEY", _KEY)
    with open_state_store(control_root=tmp_path) as store:
        store.objects.upsert(_UID, "work_item", state=_FROM, data={"branch": _BRANCH})
        store.external_refs.link(_UID, "github", "issue", str(_ISSUE))
    return tmp_path


@pytest.fixture
def token(repo: Path) -> dict:
    """A token from the REAL mint, so the expiry under test is the shipped one."""
    assert run_approve(
        [str(_ISSUE), "--transition", f"{_FROM}->{_TO}", "--by", "operator"],
        target_dir=repo, env={"USER": "operator"},
    ) == 0
    return json.loads(approval_token_path(repo, _ISSUE, _FROM, _TO).read_text())


def _check_at(repo: Path, now: datetime):
    from atdd.coach.gate.decision import GateContext

    return ApprovalTokenGateCheck(signing_key=_KEY, now=now.isoformat()).run(
        GateContext(
            issue_number=_ISSUE, from_phase=_FROM, to_phase=_TO, worktree=repo
        )
    )


def _expiry(token: dict) -> datetime:
    return datetime.fromisoformat(token["expires_at"])


def test_the_mint_stamps_an_expiry_of_the_decided_duration(repo: Path, token: dict) -> None:
    """The token stops being eternal, and the duration is the one that was decided.

    Asserted against ``APPROVAL_TTL`` rather than against a literal 24h, so the
    constant stays the single place the decision lives — a test restating the number
    would let the two drift and call it agreement.
    """
    assert token.get("expires_at"), (
        "the mint wrote a token with no expiry; build_token accepts expires_at= and "
        "the call site is still not passing it"
    )
    minted_ttl = _expiry(token) - datetime.fromisoformat(token["approved_at"])
    assert minted_ttl == APPROVAL_TTL, (
        f"the mint applied a TTL of {minted_ttl}, not the decided {APPROVAL_TTL}"
    )


def test_a_token_within_its_expiry_still_satisfies_the_gate(repo: Path, token: dict) -> None:
    """The guard discriminates rather than refusing everything."""
    result = _check_at(repo, _expiry(token) - timedelta(seconds=1))

    assert result.passed is True, result.message


def test_a_token_past_its_expiry_is_refused(repo: Path, token: dict) -> None:
    """An approval is granted for a bounded time, and the bound is real."""
    result = _check_at(repo, _expiry(token) + timedelta(seconds=1))

    assert result.passed is False, (
        "a token past its recorded expiry still satisfied the gate — verify_token "
        "has taken a `now` since #1525 and the consumer is still not passing one"
    )
    assert result.verdict is GateVerdict.FAIL


def test_the_refusal_names_expiry_rather_than_reading_as_malformed(
    repo: Path, token: dict
) -> None:
    """The distinction that is the whole point of this acceptance.

    "Your approval aged out, re-approve" and "this token is malformed or forged" are
    different facts demanding different responses. Before #1721 they shared one
    sentence.
    """
    message = _check_at(repo, _expiry(token) + timedelta(seconds=1)).message

    assert "EXPIRED" in message, (
        f"the refusal does not name expiry as the cause: {message!r}"
    )
    assert token["expires_at"] in message, (
        f"the refusal must quote the instant the token was valid until: {message!r}"
    )
    # The pre-#1721 sentence, asserted absent. Without this the test would pass on a
    # message that merely happened to contain the word somewhere.
    assert "signature is invalid" not in message, (
        f"an expired but perfectly valid token was reported as a signature or scope "
        f"problem, which is what it read as before this issue: {message!r}"
    )
    assert "does not match this transition" not in message, message


def test_expiry_is_established_by_elimination_not_by_a_broken_signature(
    repo: Path, token: dict
) -> None:
    """The token is INTACT when it expires — that is why the diagnosis is needed.

    If the signature were also broken at this point, "expired" could be guessed from
    any failure and the message would be right by accident. It is not: the same pure
    verifier says True without a clock and False with one, and the difference between
    those two answers is the entire evidence for the word EXPIRED.
    """
    from atdd.coach.gate.approval import verify_token

    expired_at = _expiry(token) + timedelta(seconds=1)

    assert verify_token(
        token, _ISSUE, _FROM, _TO, _KEY, branch=_BRANCH
    ) is True, "the token's signature and scope must still be valid past its expiry"
    assert verify_token(
        token, _ISSUE, _FROM, _TO, _KEY, branch=_BRANCH, now=expired_at.isoformat()
    ) is False, "only the clock may refuse it"
