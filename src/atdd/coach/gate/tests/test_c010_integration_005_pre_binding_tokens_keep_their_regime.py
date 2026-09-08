# URN: test:govern-lifecycle:operator-approval-token-gate:C010-INTEGRATION-005-pre-binding-tokens-keep-their-regime
# Acceptance: acc:govern-lifecycle:C010-INTEGRATION-005-pre-binding-tokens-keep-their-regime
# WMBT: wmbt:govern-lifecycle:C010
# Phase: GREEN
# Layer: integration
# Assertion: behavioral
"""C010-INTEGRATION-005 — the 169 older tokens are not retro-invalidated in silence.

169 approval tokens were measured live on 2026-08-03. The union of keys across all
of them is::

    ['approved_at', 'approved_by', 'from_phase', 'issue', 'signature', 'to_phase']

Not one carries ``branch`` or ``expires_at``, because the mint never passed them.
Turning the binding on at the gate could therefore refuse every token that already
exists — and it would refuse them for failing a rule that did not exist when they
were signed, which is not enforcement, it is backdating.

THE DECISION, ASSERTED RATHER THAN LEFT IMPLICIT: a token carrying NEITHER field is
read under the regime it was minted in — verified with no branch and no clock,
exactly as before. This is the same boundary #1718 drew for ``schema_version``, and
it is drawn on what the token CARRIES, not on when it was found, so it needs no
migration and no cutoff date.

AND THE REGIME IS SAID OUT LOUD. A version stamp nobody surfaces is a stamp nobody
reads (#1718's own lesson); the pass message names the pre-binding regime, so an
unbound token cannot present at the gate as a bound one.

THE LINE IS DRAWN PRECISELY. "Carries neither" is not "carries less than both": a
token with an expiry and no branch is a bound token missing a binding, not a legacy
one, and it is refused. Without that case this file would pass on an implementation
that simply skipped the branch check whenever the branch was absent — which is the
fail-open reading of the same sentence.

RED state: this file passes before #1721 too, and that is deliberate. It is the
regression half of the change — it fails only if the branch/expiry enforcement is
wired in a way that sweeps the existing corpus up with it.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from atdd.coach.gate.approval import sign_approval
from atdd.coach.gate.approval_check import ApprovalTokenGateCheck
from atdd.coach.gate.approval_paths import approval_token_path
from atdd.coach.gate.decision import GateContext
from atdd.state.smoke_evidence import open_state_store

pytestmark = [pytest.mark.platform]

_ISSUE, _FROM, _TO = 999723, "PLANNED", "RED"
_UID = "token-binds-branch-and-expiry-integration-005"
_BRANCH = "feat/token-binds-branch-and-expiry"
_KEY = "integration-operator-key"


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("ATDD_CONTROL_ROOT", str(tmp_path))
    return tmp_path


def _bind(repo: Path) -> None:
    with open_state_store(control_root=repo) as store:
        store.objects.upsert(_UID, "work_item", state=_FROM, data={"branch": _BRANCH})
        store.external_refs.link(_UID, "github", "issue", str(_ISSUE))


def _write(repo: Path, token: dict) -> None:
    path = approval_token_path(repo, _ISSUE, _FROM, _TO)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(token, indent=2) + "\n")


def _pre_binding_token() -> dict:
    """The EXACT field set measured across all 169 live tokens — nothing else.

    Hand-built rather than minted, because the mint can no longer produce this shape:
    the artifact under test is one that already exists on operators' machines.
    """
    return {
        "issue": _ISSUE,
        "from_phase": _FROM,
        "to_phase": _TO,
        "approved_by": "alecfokapu",
        "approved_at": "2026-07-01T00:00:00+00:00",
        "signature": sign_approval(_ISSUE, _FROM, _TO, _KEY),
    }


def _check(repo: Path):
    return ApprovalTokenGateCheck(signing_key=_KEY).run(
        GateContext(
            issue_number=_ISSUE, from_phase=_FROM, to_phase=_TO, worktree=repo
        )
    )


def test_a_pre_binding_token_still_opens_its_own_transition(repo: Path) -> None:
    """Versioning the signed scope is not a migration."""
    _bind(repo)
    _write(repo, _pre_binding_token())

    result = _check(repo)

    assert result.passed is True, (
        f"a token from the pre-binding corpus was refused by the new binding — all "
        f"169 live tokens would be invalidated by a rule that postdates them: "
        f"{result.message}"
    )


def test_it_passes_even_when_the_issue_has_no_resolvable_branch_binding(repo: Path) -> None:
    """A token that asserts no binding cannot be refused for one it never claimed.

    Deliberately NOT seeded: many of the 169 belong to issues whose work items are
    long gone. Making a legacy token depend on a store lookup it never participated
    in would re-introduce the invalidation this decision exists to prevent, through
    the back door of an unrelated failure.
    """
    _write(repo, _pre_binding_token())

    result = _check(repo)

    assert result.passed is True, (
        f"a pre-binding token was refused because the issue's branch could not be "
        f"resolved — it never claimed a branch: {result.message}"
    )


def test_the_gate_says_which_regime_the_token_belongs_to(repo: Path) -> None:
    """A reader can tell a bound token from a pre-binding one at the gate."""
    _bind(repo)
    _write(repo, _pre_binding_token())

    message = _check(repo).message

    assert "PRE-BINDING" in message, (
        f"the pass message does not distinguish the regime, so an unbound token "
        f"presents exactly like a bound one: {message!r}"
    )


def test_an_expiry_without_a_branch_is_not_treated_as_pre_binding(repo: Path) -> None:
    """The line is "carries neither", not "carries less than both".

    Without this case, an implementation that skipped the branch check whenever the
    branch happened to be absent would satisfy every other test in this file — and
    that is the fail-open reading, which would let a token opt out of the binding by
    omitting half of it.
    """
    _bind(repo)
    token = _pre_binding_token()
    token["expires_at"] = "2099-01-01T00:00:00+00:00"
    token["signature"] = sign_approval(
        _ISSUE, _FROM, _TO, _KEY, expires_at=token["expires_at"]
    )
    _write(repo, token)

    result = _check(repo)

    assert result.passed is False, (
        "a token carrying an expiry but no branch was accepted as pre-binding; a "
        "token can then opt out of the branch binding by omitting it"
    )
    assert "NO BRANCH BINDING" in result.message, result.message
