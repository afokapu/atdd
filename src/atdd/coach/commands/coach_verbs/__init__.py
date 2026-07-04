"""Auto-discovered ``atdd coach <verb>`` sub-verbs — the #1304 LEAD pattern.

WHY THIS EXISTS
    Umbrella #1303 retires ``atdd issue`` and splits its verbs across the
    author (planner) and coach archetypes. Each extracted verb is added by a
    SEPARATE child PR (#1304 transition, #1305 reconcile, #1307/#1308 …). If
    every child had to edit a shared dispatch table in ``coach.run_cli`` (or
    ``cli.py``), their parallel merges would collide on the same lines. This
    package removes that collision entirely.

THE CONVENTION (copy this for every new coach verb)
    1. Drop ONE new module into this package, named for the verb with
       ``-`` → ``_`` (``atdd coach reconcile`` → ``coach_verbs/reconcile.py``;
       ``atdd coach close-wmbt`` → ``coach_verbs/close_wmbt.py``).
    2. The module MUST expose exactly two names:
           VERB: str            — the CLI token (keep the hyphen if any)
           run(argv) -> int     — parses its own argv (everything AFTER the
                                   verb) and returns a process exit code.
       Keep the substantive logic in a sibling ``issue_<verb>.py`` module and
       have ``run`` delegate to it (as ``transition.py`` → ``issue_transition``),
       so this package stays a thin registration surface.
    3. That is the ONLY file you add. You edit NOTHING shared — not
       ``run_cli``, not ``cli.py``, not any registry list — so two children can
       never merge-conflict on wiring.

HOW DISPATCH WORKS
    ``coach.run_cli`` resolves a non-numeric leading token via
    :func:`resolve_verb`, which imports ``coach_verbs.<token>`` and returns its
    ``run`` when the module's ``VERB`` matches. :func:`discover` enumerates all
    verbs (used by help/tests). Nothing here is imported until a coach command
    is actually dispatched, so the fast ``atdd coach <N>`` path pays no cost.
"""
from __future__ import annotations

import importlib
import pkgutil
from typing import Callable, Dict, Optional


def resolve_verb(name: str) -> Optional[Callable[[list], int]]:
    """Return the ``run`` callable for coach verb ``name``, or ``None``.

    Maps the CLI token to a module (``-`` → ``_``), imports it, and returns
    ``run`` only when the module declares a matching ``VERB``. Returns ``None``
    for an unknown/absent verb (so the caller can fall through to the coach
    state-machine path) — it never raises for a missing module.
    """
    if not name:
        return None
    modname = name.replace("-", "_")
    if not modname.isidentifier():
        return None
    try:
        module = importlib.import_module(f"{__name__}.{modname}")
    except ModuleNotFoundError:
        return None
    verb = getattr(module, "VERB", None)
    run = getattr(module, "run", None)
    if verb == name and callable(run):
        return run
    return None


def discover() -> Dict[str, Callable[[list], int]]:
    """Return ``{verb: run}`` for every drop-in module in this package."""
    verbs: Dict[str, Callable[[list], int]] = {}
    for info in pkgutil.iter_modules(__path__):
        module = importlib.import_module(f"{__name__}.{info.name}")
        verb = getattr(module, "VERB", None)
        run = getattr(module, "run", None)
        if isinstance(verb, str) and callable(run):
            verbs[verb] = run
    return verbs
