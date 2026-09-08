# URN: test:bind-substrate-runtime:bind-substrate-runtime:L002-SMOKE-001
# Acceptance: acc:bind-substrate-runtime:L002-SMOKE-001-real-flat-sibling-project-enforces-from-every-checkout
# WMBT: wmbt:bind-substrate-runtime:L002
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
# Smoke: true

"""L002-SMOKE-001 — over a real project, the verdict is the same from every checkout.

The unit acceptances pin the resolver and the report against fixtures. This one
builds the thing the defect was found in: a REAL flat-sibling project — real
`git init`, real `git worktree add`, a real vendored provider whose `cli/scan.py`
is the actual subprocess boundary — with the lock in the shared Control Root at
the project root, where `atdd substrate bind` puts it and where no checkout is.

It then runs the real `enforce` from `main/` and from the linked worktree and
demands the same rule set and the same verdict from both. Before the fix, both
resolved past the lock entirely; whether that produced `no bound conventions` or
someone else's 64 rules depended only on what happened to sit at the toolkit
install, which is not a property of the repo under inspection at all.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from atdd.enforce.tests.conftest import install_extension_impl, install_provider, write_binding_lock

pytestmark = [pytest.mark.coach]

RULE = "acme.rule.owned"


def _git(*args: str, cwd: Path) -> None:
    r = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True)
    assert r.returncode == 0, f"git {' '.join(args)} failed: {r.stderr}"


def _real_flat_sibling_project(tmp_path: Path) -> tuple[Path, Path, Path]:
    project = tmp_path / "project"
    main = project / "main"
    main.mkdir(parents=True)
    _git("init", "-q", "-b", "main", cwd=main)
    _git("config", "user.email", "t@example.com", cwd=main)
    _git("config", "user.name", "T", cwd=main)
    (main / "README.md").write_text("seed\n", encoding="utf-8")
    _git("add", "README.md", cwd=main)
    _git("commit", "-q", "-m", "seed", cwd=main)

    # The substrate is admitted and bound at the CONTROL ROOT — the project root,
    # which is deliberately not a checkout. This is what `atdd init
    # --worktree-layout` produces and what `atdd substrate bind` writes into.
    install_provider(project, contract_version="1.1.0")
    install_extension_impl(
        project,
        ext_id="acme.extension.rules",
        convention=RULE,
        implementation_id=RULE,
        contract_version="1.1.0",
    )
    write_binding_lock(project, [{
        "convention_id": RULE,
        "disposition": "bound",
        "implementation_id": RULE,
        "workspace_id": "atdd.workspace.python-pytest",
        "contract_version": "1.1.0",
    }])
    (project / ".atdd" / "config.yaml").write_text("version: '1.0'\n", encoding="utf-8")

    worktree = project / "worktrees" / "feat-x"
    _git("worktree", "add", "-q", "-b", "feat/x", str(worktree), cwd=main)
    for checkout in (main, worktree):
        (checkout / "consumer.py").write_text("x = 1\n", encoding="utf-8")
        assert not (checkout / ".atdd" / "binding.lock.yaml").exists()
    return project, main, worktree


def test_l002_smoke_001_real_flat_sibling_project_enforces_from_every_checkout(tmp_path):
    from atdd.enforce.runner import enforce, resolve_substrate_home

    project, main, worktree = _real_flat_sibling_project(tmp_path)

    assert resolve_substrate_home(main) == project
    assert resolve_substrate_home(worktree) == project

    from_main = enforce(main)
    from_worktree = enforce(worktree)

    ids_main = sorted(v.rule_id for v in from_main.verdicts)
    ids_worktree = sorted(v.rule_id for v in from_worktree.verdicts)

    assert ids_main == [RULE], (
        f"the primary checkout enforced {ids_main or 'nothing'} — the real lock at "
        f"{project / '.atdd' / 'binding.lock.yaml'} was not reached"
    )
    assert ids_main == ids_worktree, (
        "two checkouts of one project enforced different rule sets, so the verdict "
        "depended on which directory the operator was standing in"
    )
    assert from_main.exit_code == from_worktree.exit_code

    # And each run says whose substrate produced that verdict.
    assert str(project) in from_main.report, (
        "the report does not name the substrate home the rules came from"
    )
    assert str(project) in from_worktree.report

    # The repo's OWN Control Root is not foreign. In this layout it is never the
    # checkout, so flagging it would fire on every correct run and train
    # operators to ignore the notice that exists for the toolkit fallback.
    assert "not this repo" not in from_main.report.lower(), (
        "the repo's own Control Root was flagged as a foreign substrate"
    )
    assert "not this repo" not in from_worktree.report.lower()
