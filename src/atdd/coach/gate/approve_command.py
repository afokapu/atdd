"""``atdd coach approve <N> --transition FROM->TO`` — write the operator approval token.

The operator's path to PRODUCE the #1017 approval token the
``ApprovalTokenGateCheck`` requires. It writes a signed token to
``.atdd/runtime/issue-<N>/approvals/<from>-<to>.json`` under the single shared
Control Root (#1346/#1376 — resolved by ``approval_paths``, NOT the literal
current worktree), independent of the cmux Feed. After this, the worker's
``atdd coach transition <N> <to>`` passes the operator-approval gate for that
exact transition — and only that one — from any worktree of the project, because
the gate resolves the same base this command mints against.

WHO MINTED (#1718). The token used to record ``--by or $USER or "operator"``,
which meant an agent running inside the operator's shell minted tokens naming
the operator: 162 of 169 tokens measured on 2026-08-03 name a human account and
an unknown number of those were agent mints. The actor is now OBSERVED through
``atdd.state.agent_session.resolve_session`` (#1540) and bound into the signed
scope, and ``--by`` is demoted to an annotation for the case where nothing is
observable. This closes the SILENT DEFAULT. It is not a boundary against an
agent that unsets its own session variable — see the THREAT MODEL in
``approval.py``, which this must not be read as contradicting.

WHAT IT IS FOR (#1721). #1525 built branch and expiry into ``canonical_scope`` /
``sign_approval`` / ``verify_token`` and NEITHER CALL SITE PASSED THEM, so every
token minted since replayed across branches and never expired — the binding
shipped and was never connected. This command now passes both. The branch comes
from the State Store's issue binding, never from the current directory, and the
expiry from :data:`~atdd.coach.gate.approval_binding.APPROVAL_TTL`; the reasoning
for both lives in ``approval_binding``. No signing logic changed here: #1525's is
correct, and every line #1721 added is an argument at a call site.

#1376 answers WHERE the receipt lives, #1718 answers WHAT it says produced it,
#1721 answers WHAT IT IS FOR — which branch, and for how long. The three are
independent and all are needed: a correctly attributed token at a path the gate
cannot read is as useless as a findable one that names the wrong actor, and both
are as useless as one that authorises every branch forever.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Tuple

from atdd.coach.gate.approval import (
    build_token,
    describe_attribution,
    resolve_signing_key,
)
from atdd.coach.gate.approval_binding import expiry_for, resolve_issue_branch
from atdd.coach.gate.approval_paths import approval_token_path


def _parse_transition(text: str) -> Tuple[str, str]:
    """Parse ``FROM->TO`` (or ``FROM-TO``) into upper-cased phase names."""
    separator = "->" if "->" in text else "-"
    parts = [p.strip() for p in text.split(separator) if p.strip()]
    if len(parts) != 2:
        raise ValueError(
            f"invalid --transition {text!r}; expected FROM->TO (e.g. PLANNED->RED)"
        )
    return parts[0].upper(), parts[1].upper()


def _observe_actor(env: Mapping[str, str]) -> Tuple[str, Optional[Dict[str, str]]]:
    """Observe who is minting: ``(approved_by, agent_session)``.

    Identity is READ from ambient process environment, never asked and never
    defaulted (#1718). ``resolve_session`` (#1540) matches the environment
    against the shipped provider table and returns None for a human at a plain
    shell — the same primitive ``atdd author issue`` and the post-commit hook
    already use, so no new mechanism is introduced and adding a provider stays
    one row of ``agent_session_env.yaml``.

    When a session IS observed, ``$USER`` is not the approver: an agent running
    inside the operator's shell IS ``$USER``, and recording it is exactly the
    defect that made 162 of 169 measured tokens name a human who may never have
    approved anything.
    """
    # Function-local, mirroring smoke_execution_check.py: keeps this command's
    # import surface as narrow as the coach->state seam it actually needs.
    from atdd.state.agent_session import resolve_session

    session = resolve_session(env)
    if session is None:
        return env.get("USER") or "operator", None
    return (
        f"agent:{session.provider}",
        {"provider": session.provider, "session_id": session.session_id},
    )


def run(
    argv: List[str],
    *,
    target_dir: Optional[Path] = None,
    env: Optional[Mapping[str, str]] = None,
) -> int:
    """Write the signed approval token for one transition.

    ``env`` overrides the ambient process environment the actor is observed
    from. It exists so a test can assert the same thing whether an agent or a
    human runs it; production passes nothing and reads ``os.environ``.
    """
    parser = argparse.ArgumentParser(
        prog="atdd coach approve",
        description=(
            "Record an operator-signed approval token authorizing one phase "
            "transition of one issue. The worker's `atdd issue <N> --status "
            "<to>` is refused until this token exists."
        ),
    )
    parser.add_argument("issue", type=int, help="Issue number to approve a transition for")
    parser.add_argument(
        "--transition", required=True,
        help="The transition to authorize, e.g. PLANNED->RED",
    )
    parser.add_argument(
        "--by", default=None,
        help=(
            "Identity to record when NO agent session can be observed (default: "
            "$USER). Ignored, with a note, when a session is observed — the mint "
            "records what it sees, not what it is told."
        ),
    )
    ns = parser.parse_args(argv)

    try:
        from_phase, to_phase = _parse_transition(ns.transition)
    except ValueError as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-12-01
        # CLI arg error surfaced to the operator (print + non-zero exit), not a
        # swallowed runtime fault — mirrors the cli.py issue-review parse path.
        print(f"Error: {exc}")
        return 1

    start = target_dir or Path.cwd()

    # #1721: what the approval is FOR. Resolved from the State Store's issue
    # binding, not from `git rev-parse` in this directory — see approval_binding
    # for why cwd would re-create the coupling #1376 removed. Asked BEFORE the
    # token directory is created, so a refusal leaves nothing behind.
    binding = resolve_issue_branch(start, ns.issue)
    if not binding:
        # REFUSE rather than mint unbound. Falling back to a branchless token
        # would manufacture a fresh pre-#1525-regime artifact — valid on every
        # branch, forever — which is the exact defect this issue closes. The 169
        # legacy tokens are tolerated because they predate the binding; there is
        # no reason to add a 170th.
        print(f"Error: cannot mint an approval for #{ns.issue} — {binding.reason}")
        return 1

    # #1376: mint against the SHARED Control Root (#1346), the same base
    # ApprovalTokenGateCheck reads from. `start` is the literal current worktree
    # and only a STARTING POINT for that resolution; minting at it put the token
    # somewhere a gate evaluating from a sibling worktree could not see (measured
    # in the #1307 walk). One resolution at both ends is what makes the token a
    # receipt rather than a file whose visibility depends on which directory the
    # operator stood in.
    token_path = approval_token_path(start, ns.issue, from_phase, to_phase)
    token_path.parent.mkdir(parents=True, exist_ok=True)

    approved_by, agent_session = _observe_actor(os.environ if env is None else env)
    if ns.by:
        if agent_session is None:
            # Nothing observed to contradict, so the operator's annotation stands.
            approved_by = ns.by
        else:
            # An observation beats a claim. Say so rather than swallowing the flag:
            # a silently ignored --by is how a caller ends up believing the token
            # says something it does not.
            print(
                f"Note: --by {ns.by!r} not recorded — an agent session "
                f"({agent_session['provider']}:{agent_session['session_id']}) was "
                f"observed, and the observed actor is what the token records."
            )

    approved_at = datetime.now(timezone.utc)
    expires_at = expiry_for(approved_at)
    token = build_token(
        ns.issue, from_phase, to_phase,
        approved_by=approved_by,
        approved_at=approved_at.isoformat(),
        agent_session=agent_session,
        branch=binding.branch,
        expires_at=expires_at,
        key=resolve_signing_key(),
    )
    token_path.write_text(json.dumps(token, indent=2) + "\n")
    print(
        f"✓ approved {from_phase}->{to_phase} for issue #{ns.issue} "
        f"({describe_attribution(token)})"
    )
    # Both bindings are STATED, because both are refusal conditions the operator
    # will meet later and neither is legible in the path or the attribution line.
    # An approval whose two limits are invisible at the moment it is granted is
    # how a gate ends up refusing for a reason nobody was told about.
    print(f"  bound to branch {binding.branch} — valid until {expires_at}")
    # The token path stays the LAST line: `atdd coach approve`'s output is parsed
    # for it (C012-SMOKE-001 takes the real path from the real command rather than
    # assuming one), so anything added below would silently break that reader.
    print(f"  token: {token_path}")
    return 0
