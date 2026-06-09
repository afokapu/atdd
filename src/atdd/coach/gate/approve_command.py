"""``atdd coach approve <N> --transition FROM->TO`` — write the operator approval token.

The operator's path to PRODUCE the #1017 approval token the
``ApprovalTokenGateCheck`` requires. It writes a signed token to
``.atdd/runtime/issue-<N>/approvals/<from>-<to>.json`` (relative to the
worktree), independent of the cmux Feed. After this, the worker's
``atdd issue <N> --status <to>`` passes the operator-approval gate for that exact
transition — and only that one.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

from atdd.coach.gate.approval import (
    approval_relpath,
    build_token,
    resolve_signing_key,
)


def _parse_transition(text: str) -> Tuple[str, str]:
    """Parse ``FROM->TO`` (or ``FROM-TO``) into upper-cased phase names."""
    separator = "->" if "->" in text else "-"
    parts = [p.strip() for p in text.split(separator) if p.strip()]
    if len(parts) != 2:
        raise ValueError(
            f"invalid --transition {text!r}; expected FROM->TO (e.g. PLANNED->RED)"
        )
    return parts[0].upper(), parts[1].upper()


def run(argv: List[str], *, target_dir: Optional[Path] = None) -> int:
    """Write the operator-signed approval token for one transition."""
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
        help="Operator identity recorded in the token (defaults to $USER)",
    )
    ns = parser.parse_args(argv)

    try:
        from_phase, to_phase = _parse_transition(ns.transition)
    except ValueError as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-12-01
        # CLI arg error surfaced to the operator (print + non-zero exit), not a
        # swallowed runtime fault — mirrors the cli.py issue-review parse path.
        print(f"Error: {exc}")
        return 1

    root = target_dir or Path.cwd()
    rel = approval_relpath(ns.issue, from_phase, to_phase)
    token_path = root / rel
    token_path.parent.mkdir(parents=True, exist_ok=True)

    approved_by = ns.by or os.environ.get("USER") or "operator"
    token = build_token(
        ns.issue, from_phase, to_phase,
        approved_by=approved_by,
        approved_at=datetime.now(timezone.utc).isoformat(),
        key=resolve_signing_key(),
    )
    token_path.write_text(json.dumps(token, indent=2) + "\n")
    print(
        f"✓ operator approved {from_phase}->{to_phase} for issue #{ns.issue} "
        f"(by {approved_by}): {rel}"
    )
    return 0
