"""Shared fixtures for the run-upgrade-unattended RED tests (#1628).

The API these tests drive does not exist yet — that is the point. They are the
spec handed to GREEN:

``resolve_confirmation(explicit_yes, isatty) -> bool``
    The Y007 resolver, mirroring ``coach.resolve_no_prompt`` (coach.py:255):
    an explicit flag wins; absent one, the answer is taken from whether stdin
    is a terminal. True means "proceed without prompting".

``upgrade_lock_path() -> Path``
    The E008 lock identity. Scoped to the *install* being mutated, never to a
    checkout — sixty worktrees have sixty ``.atdd/`` roots and would serialise
    against nothing.

``upgrade_lock(timeout=...)``
    Context manager taking that lock. Raises ``UpgradeLockUnavailable`` when
    the bounded wait expires. No bypass.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional


def write_config(repo: Path, last_version: str) -> Path:
    """Materialise a minimal ATDD repo config with a stamped toolkit version."""
    (repo / ".atdd").mkdir(parents=True, exist_ok=True)
    cfg = repo / ".atdd" / "config.yaml"
    cfg.write_text(f"toolkit:\n  last_version: {last_version}\n")
    return cfg


def exploding_input(prompt: str = "") -> str:
    """Stand-in for ``builtins.input`` that reproduces the field failure.

    upgrader.py:56 raised exactly this when a worker with no controlling
    terminal reached the prompt. Any test that patches this in and still sees
    it raised has caught the defect rather than described it.
    """
    raise EOFError("EOF when reading a line")


def upgrader_attr(name: str):
    """Return an attribute of the upgrader module, or None when absent.

    Lets a RED test assert on a symbol that does not exist yet without an
    ImportError masking the real assertion message.
    """
    import atdd.coach.commands.upgrader as upgrader

    return getattr(upgrader, name, None)


def require_symbol(name: str):
    """Fetch an upgrader symbol, failing with the spec if it is missing."""
    attr = upgrader_attr(name)
    assert attr is not None, (
        f"atdd.coach.commands.upgrader.{name} does not exist. "
        f"#1628 requires it — see the module docstring of "
        f"_upgrade_unattended_helpers for the contract."
    )
    return attr


def find_upgrader_source() -> str:
    """Read upgrader.py off disk for the static-scan assertions."""
    import atdd.coach.commands.upgrader as upgrader

    return Path(upgrader.__file__).read_text(encoding="utf-8")
