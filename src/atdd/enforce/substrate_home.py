"""Where a run's substrate lives, and saying so (#1848).

Lifted out of :mod:`atdd.enforce.runner` because it is one cohesive question —
*whose* `.atdd/binding.lock.yaml` is this run enforcing, and does the report make
that legible — and because answering it honestly needs more prose than a single
accessor in a module that already does provider spawning and verdict rendering.

The resolution order and the provenance line are documented on the functions
themselves; the short version is that the lock is written to the Control Root,
which in the flat-sibling layout is no checkout at all, so resolving it against
the caller found it from nowhere and the miss was absorbed by a fallback.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

__all__ = [
    "resolve_substrate_home",
    "substrate_provenance",
    "no_bound_report",
    "toolkit_root",
]


def toolkit_root() -> Path:
    """Repo root of the ATDD package shipping this runner (fallback substrate)."""
    # src/atdd/enforce/runner.py -> parents: [0]=enforce [1]=atdd [2]=src [3]=repo
    return Path(__file__).resolve().parents[3]


def _control_root_or_none(repo_root: Path) -> Optional[Path]:
    """The shared Control Root for ``repo_root``, or None when unresolvable.

    Delegates to the state layer's resolver so enforcement reads the lock from
    the same place admission wrote it, including the ``ATDD_CONTROL_ROOT``
    override and the flat-sibling anchoring on ``<project>/main/.git``.

    Never raises: an unresolvable layout falls through to the next candidate
    rather than turning a placement question into a command failure.
    """
    try:
        from atdd.state.paths import resolve_control_root

        return resolve_control_root(Path(repo_root)).control_root
    except Exception:  # atdd:suppress(coder.logging.coach-silent-swallow)
        return None


def resolve_substrate_home(repo_root: Path) -> Path:
    """Where ``.atdd/binding.lock.yaml`` + vendored providers live for this run.

    Three candidates, in order:

    1. the caller's own checkout — a hermetic single-repo substrate wins, so a
       repo that vendors its own lock keeps resolving to itself;
    2. the shared **Control Root** — in the flat-sibling layout this is the
       PROJECT root (``main/``'s parent), which is deliberately not a checkout;
    3. the toolkit install, so an un-bound consumer still gets the toolkit's
       bound rules enforced over its code.

    (2) is the fix for #1848. ``atdd substrate bind`` writes the lock to the
    Control Root, and in the layout ``atdd init --worktree-layout`` creates that
    directory is no checkout at all — so checking only (1) missed the lock from
    ``main/``, missed it from every worktree, and fell through to (3). The miss
    was absorbed rather than reported: a repo with a fully bound provider was
    told ``no bound conventions — clean no-op`` and given exit 0, from every
    directory anyone stands in.
    """
    repo_root = Path(repo_root)
    if (repo_root / ".atdd" / "binding.lock.yaml").is_file():
        return repo_root

    control_root = _control_root_or_none(repo_root)
    if control_root is not None and (control_root / ".atdd" / "binding.lock.yaml").is_file():
        return control_root

    return toolkit_root()


def substrate_provenance(repo_root: Path, substrate_home: Path) -> str:
    """One line naming the substrate a run used, plus a flag when it is foreign.

    Every report carries this, empty verdict set or not (#1848). The fallback in
    :func:`resolve_substrate_home` does not merely enforce nothing when a repo's
    lock is unreachable — it reads the TOOLKIT's lock and runs that rule set over
    the caller's code, reporting e.g. ``PASS — 64 rule(s) enforced`` for rules the
    caller never admitted. Unnamed, that is indistinguishable from the caller's
    own clean result.

    A repo enforcing its own substrate gets the plain line and no flag, so the
    flag keeps meaning something.
    """
    lines = [f"  substrate home: {substrate_home}"]

    # The repo's own Control Root is NOT foreign — in the flat-sibling layout it
    # is never the checkout, and flagging it would fire on every correct run and
    # teach operators to ignore the notice. Only the toolkit fallback is foreign:
    # that substrate belongs to a different repository.
    if Path(substrate_home) == toolkit_root() and Path(substrate_home) != Path(repo_root):
        lines += [
            "  NOTE: that is the toolkit's own substrate, NOT THIS REPO — no",
            f"        binding.lock.yaml was found under {repo_root} or its Control",
            "        Root. If you expected your own rules, check where",
            "        `atdd substrate bind` wrote the lock.",
        ]
    return "\n".join(lines)


def no_bound_report(repo_root: Path, substrate_home: Path) -> str:
    """The empty-set report, naming the directory that was actually searched."""
    return "enforce: no bound conventions — clean no-op.\n" + substrate_provenance(
        repo_root, substrate_home
    )


