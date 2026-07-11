"""``atdd state`` merge-authority verbs (#1400 enforce-merge-authority).

The operator- and CI-facing surface over the merge-authority spine:

- ``atdd state trailers [--commit REF|--message-file F]`` — lift a commit message into
  the schema-typed ATDD trailer group, or refuse it naming the offending trailer (D001,
  E001).
- ``atdd state merge-authority [--base REF] [--check NAME]`` — run the section-4
  required-check set; non-zero when *any* check fails (C001, C002, C003, E002).
- ``atdd state policy-check`` — the policy and the workflow are equal sets, and branch
  protection admits no bypass and no stale branch (D002).
- ``atdd state disposition-check`` — every convention node this train authors ships
  strict, or a paid-for advisory (C004).

Exit codes are the contract CI relies on: ``0`` admitted, ``1`` refused with a report
naming the object, the clause, and both sides of every disagreement.

Every verb runs with **zero** sync providers registered and reads no GitHub API — which
is what lets the whole gate run against a bare git remote (I7).

Dependency discipline: stdlib + ``atdd.state`` only.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import yaml

from atdd.state import dispositions, merge_authority, policy
from atdd.state.merge_authority import MergeAuthorityError, REQUIRED_CHECKS
from atdd.state.trailers import TrailerParseError, parse_trailers

_log = logging.getLogger(__name__)

#: The ``atdd state`` sub-commands this module owns.
OPS = ("trailers", "merge-authority", "policy-check", "disposition-check")


def add_parsers(sub) -> None:
    """Register the merge-authority verbs on the ``atdd state`` sub-parser."""
    tr = sub.add_parser("trailers", help="Parse a commit's ATDD trailer group (refuses malformed).")
    source = tr.add_mutually_exclusive_group()
    source.add_argument("--commit", default="HEAD", help="Commit to read (default: HEAD).")
    source.add_argument("--message-file", default=None, help="Read the message from a file.")
    tr.add_argument("--root", default=None, help="Repository root (default: cwd).")

    ma = sub.add_parser(
        "merge-authority",
        help="CI gate: run the section-4 required-check set over the projection diff.")
    ma.add_argument("--base", default=None,
                    help="Base ref the diff is taken against (e.g. origin/main).")
    ma.add_argument("--head", default="HEAD", help="Head ref (default: HEAD).")
    ma.add_argument("--check", default=None, choices=list(REQUIRED_CHECKS),
                    help="Run one check instead of the whole set.")
    ma.add_argument("--actor", default="",
                    help="The writer of the diff (a 'bot:'-prefixed actor is an extension).")
    ma.add_argument("--root", default=None, help="Repository root (default: cwd).")

    pol = sub.add_parser(
        "policy-check",
        help="Prove the required-check policy and the merge-authority workflow are equal sets.")
    pol.add_argument("--root", default=None, help="Repository root (default: cwd).")

    dis = sub.add_parser(
        "disposition-check",
        help="Prove every convention node this train authors ships strict (or a paid advisory).")
    dis.add_argument("--train", default=dispositions.TRAIN_ID, help="The authoring train.")
    dis.add_argument("--root", default=None, help="Repository root (default: cwd).")


def _root(args) -> Path:
    return Path(getattr(args, "root", None) or Path.cwd()).resolve()


def _cmd_trailers(args) -> int:
    if args.message_file:
        message = Path(args.message_file).read_text(encoding="utf-8")
    else:
        try:
            message = merge_authority.commit_message(_root(args), args.commit)
        except MergeAuthorityError as exc:
            print(f"ERROR: {exc}")
            return 1
    try:
        block = parse_trailers(message)
    except TrailerParseError as exc:
        # Named, not merely refused: the author has to know *which* trailer to amend.
        print(f"ERROR: {exc}")
        for key in exc.keys:
            print(f"  offending trailer: {key}")
        return 1
    print(yaml.safe_dump(block.as_document(), sort_keys=True, default_flow_style=False).rstrip())
    return 0


def _cmd_merge_authority(args) -> int:
    try:
        result = merge_authority.run_repo(
            _root(args),
            base_ref=args.base,
            head_ref=args.head,
            actor=args.actor,
            only=[args.check] if args.check else None,
        )
    except MergeAuthorityError as exc:
        _log.warning("merge-authority run could not be performed", extra={"error": str(exc)})
        print(f"ERROR: {exc}")
        return 1
    print(result.render())
    return result.exit_code


def _cmd_policy_check(args) -> int:
    try:
        report = policy.check_policy(_root(args))
    except policy.PolicyError as exc:
        print(f"ERROR: {exc}")
        return 1
    print(report.render())
    return 0 if report.ok else 1


def _cmd_disposition_check(args) -> int:
    report = dispositions.scan_conventions(_root(args), train=args.train)
    print(report.render())
    return 0 if report.ok else 1


def dispatch(args) -> int:
    """Run the merge-authority verb named by ``args.op``."""
    handlers = {
        "trailers": _cmd_trailers,
        "merge-authority": _cmd_merge_authority,
        "policy-check": _cmd_policy_check,
        "disposition-check": _cmd_disposition_check,
    }
    return handlers[args.op](args)
