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

WHETHER THE EDGE IS LIVE AT ALL (#1735). This command parsed ``FROM->TO``,
resolved a key, signed and wrote, reading NO issue state and validating the edge
against NOTHING. Observed 2026-08-03: #1726 had all five of its transitions
REFUSED by the template gate while both of its ``approve`` calls SUCCEEDED,
leaving tokens for ``PLANNED->RED`` and ``SMOKE->REFACTOR`` on the enforcement
surface for an issue sitting at ``INIT``. Correctly attributed, cryptographically
sound, at the right path — authorising two edges the issue had never crossed. The
mint now refuses unless the phase machine declares the edge AND the issue is
standing on it. See ``phase_edges``.

This is a PRECONDITION, not gate execution: running the edge's own gates at mint
time is #1670's slice C and is blocked. A gate cannot be run for an edge the issue
is not standing on, so this question is logically prior and needs no gate at all.

FOUR QUESTIONS, FOUR ISSUES, ALL INDEPENDENT. #1376 answers WHERE the receipt
lives, #1718 answers WHAT it says produced it, #1721 answers WHAT IT IS FOR —
which branch, and for how long — and #1735 answers WHETHER THE EDGE WAS LIVE at
all. All four are needed: a correctly attributed token at a path the gate cannot
read is as useless as a findable one that names the wrong actor; both are as
useless as one that authorises every branch forever; and all three are worse than
useless if they authorise a transition the issue was never in a position to make.
Provenance, scope and certification are different properties, and fixing any one
of them does not touch the others.
"""
from __future__ import annotations

import argparse
import json
import logging
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
from atdd.coach.gate.phase_edges import (
    PhaseMachineUnavailable,
    phase_machine,
    resolve_issue_phase,
)

logger = logging.getLogger(__name__)


def _parse_transition(text: str) -> Tuple[str, str]:
    """Parse ``FROM->TO`` into two phase names THE LIFECYCLE ACTUALLY DECLARES.

    #1735: this used to split on ``->``, upper-case both halves and return them,
    validated against nothing — so ``--transition 'BANANA->MOON'`` produced a
    signed token for an edge that does not exist, and ``INIT->RED`` one for an
    edge that exists nowhere in the machine. Both halves are now checked against
    ``phase_machine.convention.yaml``:

    * each name must BE a declared phase (vocabulary), and
    * ``TO`` must be reachable from ``FROM`` (legality).

    Both are properties of the string alone — no issue state — so they live here,
    in the function #1735 names, and surface through ``run``'s existing
    ``ValueError`` channel. WHERE THE ISSUE IS STANDING is a separate question and
    is asked separately; see ``run``.

    Raises:
        ValueError: unparseable, unknown phase, or an edge the machine does not
            declare. The message enumerates the legal alternatives, because a
            refusal an operator cannot act on is barely better than the mint it
            replaces.
        PhaseMachineUnavailable: the declared lifecycle could not be read. NOT
            downgraded to a permissive parse — see ``phase_edges``.
    """
    separator = "->" if "->" in text else "-"
    parts = [p.strip() for p in text.split(separator) if p.strip()]
    if len(parts) != 2:
        raise ValueError(
            f"invalid --transition {text!r}; expected FROM->TO (e.g. PLANNED->RED)"
        )
    from_phase, to_phase = parts[0].upper(), parts[1].upper()
    _reject_undeclared_edge(from_phase, to_phase, text)
    return from_phase, to_phase


def _reject_undeclared_edge(from_phase: str, to_phase: str, text: str) -> None:
    """Raise unless the lifecycle declares both phases AND the edge between them.

    Split out of :func:`_parse_transition` so parsing and judging are separate
    (and so neither carries the other's branches — ``_parse_transition`` took
    ``coder.refactor.complexity-cyclomatic`` when they were one function). The
    split is also the honest one: the caller above turns a string into two names,
    and this turns two names into a verdict about the lifecycle.
    """
    machine = phase_machine()
    for name in (from_phase, to_phase):
        if name not in machine:
            raise ValueError(
                f"unknown phase {name!r} in --transition {text!r}; the lifecycle "
                f"declares {', '.join(sorted(machine))}"
            )
    if to_phase not in machine[from_phase]:
        reachable = ", ".join(machine[from_phase]) or "nothing (it is a terminal phase)"
        raise ValueError(
            f"{from_phase}->{to_phase} is not an edge the lifecycle declares; "
            f"from {from_phase} you may go to {reachable}"
        )


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
    except ValueError as exc:
        # A REFUSED MINT IS WORTH A RECORD, not only a line on the operator's
        # terminal. `print` reaches whoever is watching and nowhere else; the log
        # is what a later audit of "why does this issue have no token" can find.
        # That is the same argument #1670 makes about gates that cannot say why
        # they refused, applied to the mint — so this logs AND prints, which is
        # what coder.logging.coach-silent-swallow asks for, instead of carrying an
        # inline suppression marker past it (#1680 counts 84 of those already).
        logger.warning(
            "approval mint refused: the transition could not be parsed or is not "
            "an edge the lifecycle declares",
            extra={"issue": ns.issue, "transition": ns.transition, "error": str(exc)},
        )
        print(f"Error: {exc}")
        return 1
    except PhaseMachineUnavailable as exc:
        # FAIL CLOSED. Without the declared machine no edge can be judged legal,
        # and the mint writes an authorisation — so "I could not check" must
        # refuse. Degrading to a permissive parse here is the failure this issue
        # exists to close, arrived at from the other direction.
        logger.warning(
            "approval mint refused: the phase machine could not be read, so no "
            "edge could be judged legal",
            extra={"issue": ns.issue, "transition": ns.transition, "error": str(exc)},
        )
        print(f"Error: cannot validate the transition — {exc}")
        return 1

    start = target_dir or Path.cwd()

    # #1735: is the issue STANDING on this edge? The mint read no issue state at
    # all, so two tokens were written for #1726 — PLANNED->RED and
    # SMOKE->REFACTOR — while it sat at INIT with all five of its transitions
    # freshly REFUSED. Those tokens were not inert: each would satisfy
    # ApprovalTokenGateCheck for its exact tuple the moment the issue ever reached
    # that edge. Asked BEFORE the token directory is created, so a refusal leaves
    # nothing behind.
    #
    # A PRECONDITION, NOT A GATE RUN. Running the edge's own gates at mint time is
    # #1670's slice C and is blocked on #1632/#1643. This is the narrower question
    # that is logically prior: a gate cannot be run for an edge the issue is not
    # standing on. It resolves the work item through external_refs first and fails
    # closed when it cannot — the shape SmokeExecutionGateCheck already uses.
    standing = resolve_issue_phase(start, ns.issue)
    if not standing:
        print(f"Error: cannot approve a transition for #{ns.issue} — {standing.reason}")
        return 1
    if standing.phase != from_phase:
        # REFUSE, DO NOT WARN. A written token is consumable; a warning is not a
        # refusal. And NAME the phase the issue is actually on — the operator's
        # next move is either to advance the issue or to approve a different edge,
        # and they cannot choose between those without being told which one this is.
        reachable = ", ".join(phase_machine().get(standing.phase, ())) or "nothing"
        print(
            f"Error: #{ns.issue} is at {standing.phase}, not {from_phase} — refusing "
            f"to mint an approval for an edge it is not standing on.\n"
            f"  From {standing.phase} the edges are: {reachable}\n"
            f"  Approve the edge it is on, or advance the issue first."
        )
        return 1

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
