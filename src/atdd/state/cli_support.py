"""Shared argparse scaffolding for the ``atdd state`` verb modules.

Every verb the State Store CLI registers has the same shape: a sub-parser, its own options,
and the ``--root`` that says where to start looking for the Control Root. Spelling that out a
statement at a time, once per verb, across six modules is how six modules come to share the
same eleven lines — and why a change to what ``--root`` means had to be made in six places.

A verb declared through :func:`add_verb` is one statement, and ``--root`` is declared once.

Dependency discipline: stdlib only.
"""
from __future__ import annotations

import argparse
from typing import Any, Dict, Optional, Tuple

#: The help most verbs give ``--root``: they resolve a repository.
REPO_ROOT_HELP = "Repository root (default: cwd)."

#: The help the store/layout verbs give it: they resolve a Control Root by walking up.
START_DIR_HELP = "Starting directory (default: cwd)."

#: ``root=NO_ROOT`` declares a verb that takes no ``--root`` at all.
NO_ROOT = "<no --root>"

#: One ``add_argument`` call, held as data.
Option = Tuple[Tuple[str, ...], Dict[str, Any]]


def opt(*flags: str, **kwargs: Any) -> Option:
    """One ``add_argument`` call, deferred — so a verb can be declared in a single statement."""
    return flags, kwargs


def add_verb(
    sub,
    name: str,
    help: str,
    *options: Option,
    root: Optional[str] = REPO_ROOT_HELP,
) -> argparse.ArgumentParser:
    """Register one ``atdd state`` verb: its help, then its options, then its ``--root``.

    ``--root`` goes last, which is where every hand-rolled verb already put it, so ``--help``
    reads exactly as it did. ``root=NO_ROOT`` opts a verb out of it entirely; ``root=None``
    registers it with no help text of its own.
    """
    parser = sub.add_parser(name, help=help)
    for flags, kwargs in options:
        parser.add_argument(*flags, **kwargs)
    if root != NO_ROOT:
        parser.add_argument("--root", default=None, help=root)
    return parser
