# Component: component:author-atdd-substrate:substrate-spine:AuthorSpine:backend:application
"""`atdd author` — author schema-valid ATDD substrate artifacts by construction.

This module is the shared spine for the `author-atdd-substrate` wagon. Every
per-kind writer (convention-node, relationship, scope, gate) routes through
``validate_author_input`` before any write path runs, so no invalid role, id,
or path ever reaches disk (WMBT C001). Per-kind writers land in follow-up
slices (E001/E002/E003/E004); this module owns the CLI skeleton + validation.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

# The four ATDD convention-owning roles. `reviewer` is a spawn persona, not a
# convention role, so it is intentionally excluded.
ROLES: tuple[str, ...] = ("planner", "tester", "coder", "coach")

# A rule_id is dot-separated lowercase kebab segments, e.g.
# `coder.green.component-urn-marker-is`. No uppercase, no underscores, and at
# least two segments (role prefix + family/slug).
_RULE_ID_RE = re.compile(r"^[a-z][a-z0-9-]*(?:\.[a-z][a-z0-9-]*)+$")

_SRC_ROOT = os.path.join("src", "atdd")


class AuthorInputError(Exception):
    """Raised when the shared spine rejects an author input.

    Carries the offending ``field`` (``"role"`` / ``"rule_id"`` / ``"path"``)
    so callers and tests can assert *why* the input was refused.
    """

    def __init__(self, field: str, message: str) -> None:
        super().__init__(message)
        self.field = field


def validate_author_input(role: str, rule_id: str, path: Path) -> None:
    """Validate role, rule_id and path before any per-kind writer runs.

    Raises ``AuthorInputError`` (with ``.field``) on the first violation:
      * ``role`` not one of :data:`ROLES`;
      * ``rule_id`` not lowercase-kebab dot-segments, or not prefixed by ``role``;
      * ``path`` escaping the canonical ``src/atdd/`` home (e.g. ``..`` traversal).
    Returns ``None`` when the input is well-formed.
    """
    if role not in ROLES:
        raise AuthorInputError(
            "role", f"invalid role {role!r}; expected one of {', '.join(ROLES)}"
        )

    if not _RULE_ID_RE.match(rule_id) or rule_id.split(".", 1)[0] != role:
        raise AuthorInputError(
            "rule_id",
            f"invalid rule_id {rule_id!r}; must be lowercase kebab dot-segments "
            f"prefixed by the role {role!r} (e.g. {role}.green.some-slug)",
        )

    norm = os.path.normpath(str(path))
    if norm.startswith("..") or not (
        norm == _SRC_ROOT or norm.startswith(_SRC_ROOT + os.sep)
    ):
        raise AuthorInputError(
            "path", f"path {str(path)!r} escapes the canonical home under {_SRC_ROOT}/"
        )


def _node_path(role: str, rule_id: str) -> Path:
    """Canonical flat per-role home for a convention-node file (spec §3.1)."""
    return Path(_SRC_ROOT) / role / "conventions" / "nodes" / f"{rule_id}.convention.yaml"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="atdd author",
        description="Author schema-valid ATDD substrate artifacts by construction.",
    )
    sub = parser.add_subparsers(dest="kind", required=True)

    cn = sub.add_parser("convention-node", help="author a flat per-role convention node")
    cn.add_argument("--role", required=True, help="convention-owning role")
    cn.add_argument("--rule-id", required=True, dest="rule_id", help="canonical rule_id")

    return parser


def run(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)

    if args.kind == "convention-node":
        path = _node_path(args.role, args.rule_id)
        try:
            validate_author_input(args.role, args.rule_id, path)
        except AuthorInputError as exc:
            print(f"atdd author: {exc}", file=sys.stderr)
            return 2
        # Writer is implemented in the convention-node slice (E001). The spine
        # has validated the input; until the writer lands, refuse to claim a
        # write so the SMOKE never sees a partial artifact.
        print(
            "atdd author: convention-node writer not yet implemented (E001)",
            file=sys.stderr,
        )
        return 3

    return 2
