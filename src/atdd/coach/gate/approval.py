"""Pure operator-approval-token logic for the #1017 gate check (registered into #1020).

A token is an operator-signed filesystem artifact authorizing exactly ONE phase
transition of one issue on ONE branch for a BOUNDED time:
``(issue, from_phase, to_phase, branch, expires_at)``. This module is the pure,
stdlib-only core — it computes the canonical scope, signs it (HMAC-SHA256),
builds the token dict, and verifies a token against a transition. The filesystem
I/O lives in the ``approval_check`` sibling, so this verdict logic stays
unit-testable in isolation (the #955/#865/#1020 compliance bar — no subprocess,
no network).

The token is INDEPENDENT of the cmux Feed: presence is checked on disk, so the
Feed's ~120s soft-expiry can neither satisfy nor bypass the gate, and an absent
operator leaves the worker BLOCKED rather than leaking through (#1017).

THREAT MODEL (#1525 — read this before trusting the token as a control)
-----------------------------------------------------------------------
Binding the branch and an expiry into the signed scope closes ACCIDENT and
DRIFT: an approval the operator signs for one branch no longer verifies on an
unrelated branch (the replay-across-branch defect — 19 of 19 main-signed tokens
verifying from foreign worktrees, measured 2026-07-18), and a token no longer
verifies forever, so a stale approval cannot survive into a later transition.

It closes NOTHING against a MISBEHAVING AGENT. ``resolve_signing_key`` falls
back to ``DEFAULT_SIGNING_KEY``, a public constant checked into this repo, so
any process that can import this module can also ``build_token`` — mint a fresh,
correctly-branched, unexpired token for any issue in one line. Branch+expiry
make the artifact mean what its name says; they do not make it unforgeable.
Only an asymmetric scheme with the signing key OUTSIDE the agent's reach (the
open Decision 1 for the operator; ``ssh-keygen -Y sign``/``-Y verify`` was the
recommendation) would make this a boundary against a hostile worker. Do not
describe branch+expiry as a security boundary — it is not one.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Mapping, Optional

logger = logging.getLogger(__name__)

# Used when no operator signing key is configured. Signing binds the token to its
# exact scope (a PLANNED->RED token can never be replayed for RED->GREEN, nor
# across branches, nor past its expiry); a configured
# ``ATDD_APPROVAL_SIGNING_KEY`` additionally makes forging require the secret.
# NOTE (#1525): with the default key this is NOT secret from the worker — see the
# THREAT MODEL in the module docstring. Do not treat the default-key path as a
# defence against a misbehaving agent.
DEFAULT_SIGNING_KEY = "atdd-operator-approval-v1"
_SIGNING_KEY_ENV = "ATDD_APPROVAL_SIGNING_KEY"


def canonical_scope(
    issue_number: int,
    from_phase: str,
    to_phase: str,
    branch: Optional[str] = None,
    expires_at: Optional[str] = None,
) -> str:
    """The signed string identifying one transition of one issue, on one branch,
    until one moment.

    Backward compatible: with no ``branch`` and no ``expires_at`` this reduces to
    the legacy ``issue:FROM:TO`` string, so tokens signed before branch/expiry
    binding (and the scope-isolation contract in E050) verify unchanged. When
    present, ``branch`` and ``expires_at`` are folded into the signed message, so
    a signature made for one branch/expiry cannot match another and editing the
    expiry in a token invalidates its signature rather than extending its life.
    """
    scope = f"{int(issue_number)}:{from_phase.upper()}:{to_phase.upper()}"
    if branch:
        scope += f":branch={branch}"
    if expires_at:
        scope += f":expires={expires_at}"
    return scope


def sign_approval(
    issue_number: int,
    from_phase: str,
    to_phase: str,
    key: Optional[str] = None,
    *,
    branch: Optional[str] = None,
    expires_at: Optional[str] = None,
) -> str:
    """HMAC-SHA256 over the canonical scope — deterministic and scope-sensitive."""
    secret = (key or DEFAULT_SIGNING_KEY).encode("utf-8")
    msg = canonical_scope(
        issue_number, from_phase, to_phase, branch, expires_at
    ).encode("utf-8")
    return hmac.new(secret, msg, hashlib.sha256).hexdigest()


def _parse_iso(value) -> Optional[datetime]:
    """Parse an ISO-8601 instant, or return None (never raise) for fail-closed use.

    Accepts a trailing ``Z`` as UTC. Any non-string, blank, or unparseable value
    yields None so a malformed expiry rejects rather than crashes the verifier.
    """
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        # Observably react rather than swallowing: a malformed instant is a
        # fail-closed REJECTION, and the operator needs to see which value could
        # not be read (a mistyped expiry looks identical to an expired token
        # from the outside).
        logger.warning(
            "approval token: unparseable ISO-8601 instant; verification fails closed",
            extra={"value": text},
        )
        return None


def resolve_signing_key() -> Optional[str]:
    """The operator signing key from the environment, or None (=> built-in default)."""
    return os.environ.get(_SIGNING_KEY_ENV) or None


def approval_relpath(issue_number: int, from_phase: str, to_phase: str) -> Path:
    """Token path RELATIVE to the worktree (a Feed-decoupled filesystem artifact)."""
    return (
        Path(".atdd")
        / "runtime"
        / f"issue-{int(issue_number)}"
        / "approvals"
        / f"{from_phase.upper()}-{to_phase.upper()}.json"
    )


def build_token(
    issue_number: int,
    from_phase: str,
    to_phase: str,
    *,
    approved_by: str,
    approved_at: str,
    branch: Optional[str] = None,
    expires_at: Optional[str] = None,
    key: Optional[str] = None,
) -> dict:
    """Build the operator-signed token dict for one exact transition.

    When ``branch`` and/or ``expires_at`` are supplied they are bound into the
    signed scope and recorded on the token, so verification can reject the token
    on a different branch or after its expiry. Omitting both yields a
    legacy-scoped token (issue:FROM:TO) for backward compatibility.
    """
    token = {
        "issue": int(issue_number),
        "from_phase": from_phase.upper(),
        "to_phase": to_phase.upper(),
        "approved_by": approved_by,
        "approved_at": approved_at,
        "signature": sign_approval(
            issue_number, from_phase, to_phase, key,
            branch=branch, expires_at=expires_at,
        ),
    }
    if branch:
        token["branch"] = branch
    if expires_at:
        token["expires_at"] = expires_at
    return token


def verify_token(
    token_data,
    issue_number: int,
    from_phase: str,
    to_phase: str,
    key: Optional[str] = None,
    *,
    branch: Optional[str] = None,
    now: Optional[str] = None,
) -> bool:
    """True iff ``token_data`` is a correctly-signed token for THIS exact transition
    — same issue, same from/to, same ``branch``, and (when ``now`` is supplied)
    not past the token's expiry.

    Rejects (returns False) an absent/non-mapping token, a token scoped to a
    different issue or transition (scope isolation — one transition's token never
    unlocks another), a token whose signature does not match ``sign_approval``
    over the scope under ``key`` — which now folds in ``branch`` and the token's
    own ``expires_at``, so a token signed for one branch fails on another and a
    token carrying no branch fails a branch-scoped verification — and, when
    ``now`` is given, a token that is expired, undated, or carries a malformed
    expiry (fail-closed, no exception escapes the pure verifier).

    ``branch`` and ``now`` default to None, preserving the pre-#1525 contract:
    callers that pass neither get exactly the legacy issue/from/to/signature
    check (relied on by the E050 scope-isolation tests and the existing gate
    consumer). See the module THREAT MODEL — branch+expiry close accident and
    drift, not a forging agent holding the default key.
    """
    if not isinstance(token_data, Mapping):
        return False
    # Scope: the token's issue must equal this issue. Tolerate an integer-valued
    # string but reject anything non-numeric WITHOUT exception flow, so the pure
    # verifier neither swallows nor raises on a malformed token (fail-closed).
    issue_val = token_data.get("issue")
    if isinstance(issue_val, str) and issue_val.lstrip("-").isdigit():
        issue_val = int(issue_val)
    if not isinstance(issue_val, int) or isinstance(issue_val, bool) or issue_val != int(issue_number):
        return False
    if str(token_data.get("from_phase", "")).upper() != from_phase.upper():
        return False
    if str(token_data.get("to_phase", "")).upper() != to_phase.upper():
        return False
    # Signature covers the branch presented and the token's OWN expiry. A token
    # signed for branch A recomputes to a different digest under branch B (and a
    # branchless token recomputes differently from any branch-scoped request), so
    # branch binding is enforced by the signature itself. Recomputing over the
    # token's stored expiry makes the expiry tamper-evident: editing it to buy
    # more time breaks the signature rather than extending the life.
    token_expiry = token_data.get("expires_at")
    expected = sign_approval(
        issue_number, from_phase, to_phase, key,
        branch=branch,
        expires_at=token_expiry if token_expiry else None,
    )
    if not hmac.compare_digest(str(token_data.get("signature", "")), expected):
        return False
    # Expiry is enforced only when the caller supplies a clock. Without ``now``
    # the check is time-agnostic (backward compatible); with it, an undated,
    # malformed, or past-due token fails closed.
    if now is not None:
        expiry_dt = _parse_iso(token_expiry)
        now_dt = _parse_iso(now)
        if expiry_dt is None or now_dt is None:
            return False
        if now_dt > expiry_dt:
            return False
    return True
