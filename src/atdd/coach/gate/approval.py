"""Pure operator-approval-token logic for the #1017 gate check (registered into #1020).

A token is an operator-signed filesystem artifact authorizing exactly ONE phase
transition of one issue: ``(issue, from_phase, to_phase)``. This module is the
pure, stdlib-only core — it computes the canonical scope, signs it (HMAC-SHA256),
builds the token dict, and verifies a token against a transition. The filesystem
I/O lives in the ``approval_check`` sibling, so this verdict logic stays
unit-testable in isolation (the #955/#865/#1020 compliance bar — no subprocess,
no network).

The token is INDEPENDENT of the cmux Feed: presence is checked on disk, so the
Feed's ~120s soft-expiry can neither satisfy nor bypass the gate, and an absent
operator leaves the worker BLOCKED rather than leaking through (#1017).
"""
from __future__ import annotations

import hashlib
import hmac
import os
from pathlib import Path
from typing import Mapping, Optional

# Used when no operator signing key is configured. Signing still binds the token
# to its exact scope (a PLANNED->RED token can never be replayed for RED->GREEN);
# a configured ``ATDD_APPROVAL_SIGNING_KEY`` additionally makes forging require
# the secret. Either way producing a token is a deliberate operator act, not the
# daemon's rubber-stamp.
DEFAULT_SIGNING_KEY = "atdd-operator-approval-v1"
_SIGNING_KEY_ENV = "ATDD_APPROVAL_SIGNING_KEY"


def canonical_scope(issue_number: int, from_phase: str, to_phase: str) -> str:
    """The signed string identifying exactly one transition of one issue."""
    return f"{int(issue_number)}:{from_phase.upper()}:{to_phase.upper()}"


def sign_approval(
    issue_number: int, from_phase: str, to_phase: str, key: Optional[str] = None
) -> str:
    """HMAC-SHA256 over the canonical scope — deterministic and scope-sensitive."""
    secret = (key or DEFAULT_SIGNING_KEY).encode("utf-8")
    msg = canonical_scope(issue_number, from_phase, to_phase).encode("utf-8")
    return hmac.new(secret, msg, hashlib.sha256).hexdigest()


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
    key: Optional[str] = None,
) -> dict:
    """Build the operator-signed token dict for one exact transition."""
    return {
        "issue": int(issue_number),
        "from_phase": from_phase.upper(),
        "to_phase": to_phase.upper(),
        "approved_by": approved_by,
        "approved_at": approved_at,
        "signature": sign_approval(issue_number, from_phase, to_phase, key),
    }


def verify_token(
    token_data,
    issue_number: int,
    from_phase: str,
    to_phase: str,
    key: Optional[str] = None,
) -> bool:
    """True iff ``token_data`` is a correctly-signed token for THIS exact transition.

    Rejects (returns False) an absent/non-mapping token, a token scoped to a
    different issue or transition (scope isolation — one transition's token never
    unlocks another), and a token whose signature does not match
    ``sign_approval`` over the scope under ``key``.
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
    expected = sign_approval(issue_number, from_phase, to_phase, key)
    return hmac.compare_digest(str(token_data.get("signature", "")), expected)
