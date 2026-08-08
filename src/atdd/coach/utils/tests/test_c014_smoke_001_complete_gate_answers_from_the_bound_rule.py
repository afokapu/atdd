# URN: test:author-atdd-substrate:author-issue-body:C014-SMOKE-001-complete-gate-answers-from-the-bound-rule
# Acceptance: acc:author-atdd-substrate:C014-SMOKE-001-complete-gate-answers-from-the-bound-rule
# WMBT: wmbt:author-atdd-substrate:C014
# Phase: RED
# Layer: integration
"""C014-SMOKE-001 — the real COMPLETE gate answers from the bound rule.

No mocks of the policy: a throwaway git checkout driven into the state
``atdd auto-phase`` actually sees — on the default branch, at the commit the PR
landed (#1611) — the real ``IssueManager``, and the real convention registry.

An empty declaration must produce the declared violation instead of the
``total == 0`` free pass; an accurate declaration must produce none while each
claim is still reported against git.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.smoke


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=str(repo), capture_output=True, text=True, check=True,
    )
    return result.stdout.strip()


@pytest.fixture()
def landed_repo(tmp_path: Path) -> tuple[Path, str]:
    """A real checkout on ``main`` at the squash commit the PR landed."""
    origin = tmp_path / "origin.git"
    origin.mkdir()
    _git(origin, "init", "--bare", "--initial-branch=main")

    repo = tmp_path / "work"
    repo.mkdir()
    _git(repo, "init", "--initial-branch=main")
    _git(repo, "config", "user.email", "gate@example.test")
    _git(repo, "config", "user.name", "Gate Test")
    _git(repo, "remote", "add", "origin", str(origin))

    (repo / "tracked.py").write_text("original\n")
    (repo / "doomed.py").write_text("goes away\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "base")
    _git(repo, "push", "-u", "origin", "main")

    _git(repo, "checkout", "-b", "feat/work")
    (repo / "tracked.py").write_text("changed by the PR\n")
    (repo / "created.py").write_text("new\n")
    (repo / "doomed.py").unlink()
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "the PR's work")

    _git(repo, "checkout", "main")
    _git(repo, "merge", "--squash", "feat/work")
    _git(repo, "commit", "-m", "the PR's work (#1726) (#9999)")
    _git(repo, "push", "origin", "main")
    _git(repo, "branch", "-D", "feat/work")
    return repo, _git(repo, "rev-parse", "HEAD")


def _manager(repo: Path, landed: str):
    from atdd.coach.commands.issue import IssueManager

    manager = IssueManager(target_dir=repo)
    # GitHub names the commit the PR landed; this checkout already has it.
    manager._landed_commit = lambda issue_number: landed  # type: ignore[method-assign]
    return manager


def test_c014_smoke_001_empty_declaration_produces_the_declared_violation(landed_repo):
    from atdd.coach.utils.artifact_claims import RULE_MUST_BE_DECLARED

    repo, landed = landed_repo
    report = _manager(repo, landed).check_artifacts(
        {"created": [], "modified": [], "deleted": []}, issue_number=1726,
    )

    assert RULE_MUST_BE_DECLARED in {v.rule_id for v in report.violations}, (
        "the real gate still exempts an issue that declares nothing; got "
        f"{[str(v) for v in report.violations]}"
    )


def test_c014_smoke_001_the_violation_resolves_through_the_real_registry(landed_repo):
    """Severity and disposition come from the convention, not from the code."""
    from atdd.coach.utils.rule_binding import bind_rule

    repo, landed = landed_repo
    report = _manager(repo, landed).check_artifacts(
        {"created": [], "modified": [], "deleted": []}, issue_number=1726,
    )

    for violation in report.violations:
        meta = bind_rule(violation.rule_id)
        assert violation.severity == meta.severity, (
            f"{violation.rule_id} emitted severity {violation.severity} but the "
            f"convention declares {meta.severity} — severity must not be hard-coded"
        )


def test_c014_smoke_001_an_accurate_declaration_passes_and_is_still_reported(landed_repo):
    repo, landed = landed_repo
    report = _manager(repo, landed).check_artifacts(
        {"created": ["created.py"], "modified": ["tracked.py"], "deleted": ["doomed.py"]},
        issue_number=1726,
    )

    assert report.violations == (), (
        f"an accurate declaration must pass clean; got {[str(v) for v in report.violations]}"
    )
    assert report.satisfied
    rendered = "\n".join(report.messages)
    assert "created.py" in rendered and "EXISTS" in rendered, rendered
    assert "tracked.py" in rendered and "CHANGED" in rendered, rendered
    assert "doomed.py" in rendered and "CONFIRMED GONE" in rendered, rendered


def test_c014_smoke_001_a_file_the_pr_landed_but_never_declared_is_reported(landed_repo):
    """The reverse pass reads the real landed diff, not a fixture list."""
    from atdd.coach.utils.artifact_claims import RULE_MUST_BE_DECLARED

    repo, landed = landed_repo
    report = _manager(repo, landed).check_artifacts(
        {"created": ["created.py"], "modified": ["tracked.py"], "deleted": []},
        issue_number=1726,
    )

    undeclared = [
        v for v in report.violations
        if v.rule_id == RULE_MUST_BE_DECLARED and "doomed.py" in v.detail
    ]
    assert undeclared, (
        "the commit the PR landed deleted doomed.py and the claim never named it; "
        f"got {[str(v) for v in report.violations]}"
    )
