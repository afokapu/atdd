"""Shared plumbing for the C013 live-store-guard fault injections (#1582).

Every probe here drives a REAL child pytest session (``runpytest_subprocess``)
with the SHIPPED plugin enabled by name — ``-p atdd.state.live_store_guard_plugin``
— rather than reimplementing the fixtures inside the test. That distinction is
the whole point: a probe that re-declares its own copy of the guard proves only
that the copy works, and the copy is exactly what drifts from the thing actually
protecting the store.

Safety: no probe ever aims the guard at the real store. Each points
:data:`~atdd.state.live_store_guard.GUARD_TARGET_ENV` at a throwaway path under
``tmp_path``, so the fault is injected into a decoy and the production store is
never a participant.

BOUNDARY: ``author-atdd-substrate`` is a ``commons``-themed wagon, so nothing in
this tree may ``import atdd.coach`` (planner.theme.commons-coach-boundary, #970).
These helpers touch only the foundational ``atdd.state`` layer.
"""
from __future__ import annotations

import os
from pathlib import Path

#: The shipped plugin, enabled by name in every inner session.
PLUGIN = "atdd.state.live_store_guard_plugin"


def repo_root() -> Path:
    """Walk up from this file until a repo marker (pyproject.toml) is found."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").exists():
            return parent
    raise RuntimeError("could not locate repo root from " + str(here))


def inner_env(monkeypatch, *, control_root=None, guard_target=None) -> dict:
    """Arm the environment a child pytest session will inherit.

    ``runpytest_subprocess`` inherits ``os.environ``, so setting it here with
    ``monkeypatch`` both configures the child and gets restored for the parent.

    ``guard_target`` re-points the guard at a decoy: a path protects that path
    ONLY, and ``""`` protects nothing. Returns the values applied so a probe can
    assert on what it actually armed rather than on what it meant to arm.
    """
    from atdd.state.live_store_guard import CONTROL_ROOT_ENV, GUARD_TARGET_ENV

    applied: dict = {}

    # The child needs `atdd` importable: its rootdir is the pytester tmp dir, so
    # the repo's `pythonpath = ["src"]` pytest setting does not reach it.
    src = str(repo_root() / "src")
    existing = os.environ.get("PYTHONPATH", "")
    monkeypatch.setenv("PYTHONPATH", f"{src}{os.pathsep}{existing}" if existing else src)

    if control_root is not None:
        monkeypatch.setenv(CONTROL_ROOT_ENV, str(control_root))
        applied[CONTROL_ROOT_ENV] = str(control_root)
    else:
        monkeypatch.delenv(CONTROL_ROOT_ENV, raising=False)

    if guard_target is not None:
        monkeypatch.setenv(GUARD_TARGET_ENV, str(guard_target))
        applied[GUARD_TARGET_ENV] = str(guard_target)

    return applied


def write_inner_conftest(pytester) -> None:
    """Give the inner session a conftest that registers nothing of its own.

    The inner sessions deliberately run WITHOUT the repo's ``src/atdd/conftest.py``
    (its #771 git guard shells out to git in teardown, which is noise here). An
    empty conftest keeps the inner rootdir self-contained so what the probe
    observes is attributable to the guard plugin alone.
    """
    pytester.makeconftest("")
