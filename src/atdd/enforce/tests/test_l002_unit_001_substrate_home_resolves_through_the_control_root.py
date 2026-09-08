# URN: test:bind-substrate-runtime:bind-substrate-runtime:L002-UNIT-001
# Acceptance: acc:bind-substrate-runtime:L002-UNIT-001-substrate-home-resolves-through-the-control-root
# WMBT: wmbt:bind-substrate-runtime:L002
# Phase: RED
# Layer: backend.unit
# Assertion: behavioral

"""L002-UNIT-001 — the substrate home is the Control Root, not the caller's checkout.

`atdd substrate bind` writes `binding.lock.yaml` into the CONTROL ROOT. In the
flat-sibling layout — the one `atdd init --worktree-layout` creates and CLAUDE.md
mandates — the Control Root is the PROJECT root: `<project>/.atdd/`, the parent of
`main/`. It is therefore not any checkout.

`resolve_substrate_home` looked only at `<caller>/.atdd/binding.lock.yaml`. So it
missed the lock from `main/`, missed it from every linked worktree, and absorbed
the miss by falling back to the toolkit's own install — which in a pipx install
carries no lock either. The result was `enforce: no bound conventions — clean
no-op.` and exit 0, in a repo with a fully bound provider.

That is a false PASS, and it is the whole of the defect: enforcement was off in
every directory anyone stands in, and said so nowhere.

Phase RED: both resolutions return the toolkit root instead of the Control Root.
Phase GREEN: both return the Control Root, and the same bound set loads from each.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

pytestmark = [pytest.mark.coach]

LOCK = (
    "schema_version: 1.0.0\nconventions:\n"
    "- convention_id: acme.rule.owned\n  disposition: bound\n"
    "  implementation_id: acme.rule.owned\n"
    "  workspace_id: atdd.workspace.python-pytest\n  contract_version: 1.1.0\n"
)


def _git(*args: str, cwd: Path) -> None:
    r = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True)
    assert r.returncode == 0, f"git {' '.join(args)} failed: {r.stderr}"


def _flat_sibling_project(tmp_path: Path) -> tuple[Path, Path, Path]:
    """`<project>/main` + `<project>/worktrees/feat-x`, lock at `<project>/.atdd`."""
    project = tmp_path / "project"
    main = project / "main"
    main.mkdir(parents=True)
    _git("init", "-q", "-b", "main", cwd=main)
    _git("config", "user.email", "t@example.com", cwd=main)
    _git("config", "user.name", "T", cwd=main)
    (main / "README.md").write_text("seed\n", encoding="utf-8")
    _git("add", "README.md", cwd=main)
    _git("commit", "-q", "-m", "seed", cwd=main)

    # The Control Root: the project root, which is NO checkout.
    control = project / ".atdd"
    control.mkdir()
    (control / "binding.lock.yaml").write_text(LOCK, encoding="utf-8")
    (control / "config.yaml").write_text("version: '1.0'\n", encoding="utf-8")

    worktree = project / "worktrees" / "feat-x"
    _git("worktree", "add", "-q", "-b", "feat/x", str(worktree), cwd=main)

    # Neither checkout carries a lock — that is the layout, not an omission.
    assert not (main / ".atdd" / "binding.lock.yaml").exists()
    assert not (worktree / ".atdd" / "binding.lock.yaml").exists()
    return project, main, worktree


def test_l002_unit_001_substrate_home_resolves_through_the_control_root(tmp_path):
    from atdd.enforce.runner import resolve_substrate_home

    project, main, worktree = _flat_sibling_project(tmp_path)

    assert resolve_substrate_home(main) == project, (
        "from the PRIMARY checkout the substrate home must be the shared Control "
        "Root; resolving against the checkout finds no lock and silently falls "
        "back to the toolkit's own substrate"
    )
    assert resolve_substrate_home(worktree) == project, (
        "from a linked worktree — where an agent actually works — the substrate "
        "home must be the same Control Root, not a per-worktree guess"
    )


def test_l002_unit_001_same_bound_set_loads_from_every_checkout(tmp_path):
    """The point of the resolution: the verdict cannot depend on the caller's cwd."""
    from atdd.enforce.runner import _bound_conventions, resolve_substrate_home

    _project, main, worktree = _flat_sibling_project(tmp_path)

    from_main = _bound_conventions(resolve_substrate_home(main))
    from_worktree = _bound_conventions(resolve_substrate_home(worktree))

    assert [c["convention_id"] for c in from_main] == ["acme.rule.owned"], (
        "the bound set read from the primary checkout is empty — this is the "
        "'clean no-op' a consumer was shown while a provider was fully bound"
    )
    assert from_main == from_worktree, (
        "two checkouts of one project resolved different bound sets"
    )


def test_l002_unit_001_an_explicit_checkout_local_lock_still_wins(tmp_path):
    """A hermetic single-repo layout is unchanged — its own lock takes precedence."""
    from atdd.enforce.runner import resolve_substrate_home

    project, main, _worktree = _flat_sibling_project(tmp_path)
    local = main / ".atdd"
    local.mkdir(exist_ok=True)
    (local / "binding.lock.yaml").write_text(LOCK, encoding="utf-8")

    assert resolve_substrate_home(main) == main, (
        "a checkout carrying its own lock must keep resolving to itself; the "
        "Control Root walk is a fallback, not a replacement"
    )
    assert resolve_substrate_home(project / "worktrees" / "feat-x") == project
