"""Resolution seam for packaged git hooks (#1492).

`.atdd/hooks/*` used to be a snapshot copy of the packaged templates, so a hook
fix only ever reached repos initialised after it landed. The installed hooks are
now fixed-content dispatchers that exec the PACKAGED hook, which makes drift
structurally impossible: there is no copied logic left to go stale.

This module is the seam those dispatchers resolve through. It is intentionally
import-light — a git hook pays this cost on every commit.
"""

from __future__ import annotations

from pathlib import Path
from typing import List

#: Files under templates/hooks/ that are not themselves hooks.
_NON_HOOK_PREFIXES = ("__", ".")


def packaged_hooks_dir() -> Path:
    """Return the directory holding the packaged hook templates.

    Resolved from this module's own location, so it is correct for a wheel
    install, an editable install and a source checkout alike — never from a
    ``$REPO_ROOT/src/atdd/...`` guess, which is the #689/#1476 hardcoded-path
    class that leaves claude-pre-tool-use.sh inert in every consumer repo.
    """
    return Path(__file__).resolve().parent.parent / "templates" / "hooks"


def declared_hook_names() -> List[str]:
    """Return every hook name the package ships, sorted.

    This is the single source of truth for "which hooks should exist": the
    installer and the parity validator both read it, so a hook added to the
    template tree cannot be silently left uninstalled (6 of 11 were, #1492).
    """
    hooks_dir = packaged_hooks_dir()
    if not hooks_dir.is_dir():
        return []
    return sorted(
        p.name
        for p in hooks_dir.iterdir()
        if p.is_file() and not p.name.startswith(_NON_HOOK_PREFIXES)
    )


def resolve_hook_path(name: str) -> Path | None:
    """Return the packaged hook *name*, or None when it does not exist.

    None is a real answer here, not an error: the dispatcher turns it into a
    blocked operation with repair instructions, because a guard that cannot run
    must not silently allow.
    """
    if not name or "/" in name or name.startswith(_NON_HOOK_PREFIXES):
        return None
    candidate = packaged_hooks_dir() / name
    return candidate if candidate.is_file() else None


def run_hooks_path(name: str) -> int:
    """`atdd hooks path <name>` — print the packaged hook's absolute path.

    Prints nothing and exits non-zero when unresolvable, so the calling
    dispatcher's `[ -n "$_HOOK_PATH" ]` check fails closed.
    """
    resolved = resolve_hook_path(name)
    if resolved is None:
        return 1
    print(resolved)
    return 0


def run_hooks_list() -> int:
    """`atdd hooks list` — print every hook name the installed package ships."""
    for name in declared_hook_names():
        print(name)
    return 0
