# URN: test:self-compliance:branch-protection:BP-UNIT-001-verify-before-any-remote-write
# Phase: RED
# Layer: unit
# Assertion: behavioral
# Runtime: python
"""BP-UNIT-001 — verification decides whether a remote write happens at all.

    A repository already matching the expected policy is mutated zero times.

`apply_and_verify` called `apply_branch_protection` FIRST and unconditionally,
then verified the result. So every `atdd sync` — from any worktree, on any
branch, however routine — fired `gh api repos/<repo>/branches/main/protection
--method PUT` before knowing whether anything differed. #1599: the operator's
intent in a throwaway worktree is a local refresh, not repo administration.

Verification is a read and already returns the drift it found, so the ordering
was the whole defect: verify, and write only when the answer is DRIFTED or
MISSING. A DEGRADED answer — the API could not be read — must NOT write either:
"could not check" is not "is wrong", and writing on it would restore exactly the
unconditional PUT this removes.
"""
from __future__ import annotations

import pytest

from atdd.coach.commands import branch_protection as bp


@pytest.fixture()
def calls(monkeypatch) -> list:
    """Record every apply attempt without touching the network."""
    seen: list = []
    monkeypatch.setattr(bp, "apply_branch_protection",
                        lambda repo: seen.append(repo) or True)
    return seen


def _verifies(monkeypatch, status, details=()):
    monkeypatch.setattr(bp, "verify_branch_protection",
                        lambda repo: (status, list(details)))


def test_enforced_repo_is_not_written_to(monkeypatch, calls) -> None:
    _verifies(monkeypatch, bp.ProtectionStatus.ENFORCED)
    status, _ = bp.apply_and_verify("owner/repo")
    assert calls == [], "a repo already matching the policy must not be mutated"
    assert status is bp.ProtectionStatus.ENFORCED


def test_drifted_repo_is_written_to(monkeypatch, calls) -> None:
    _verifies(monkeypatch, bp.ProtectionStatus.DRIFTED, ["enforce_admins: false"])
    bp.apply_and_verify("owner/repo")
    assert calls == ["owner/repo"], "drift is exactly what the write exists to correct"


def test_missing_protection_is_written_to(monkeypatch, calls) -> None:
    _verifies(monkeypatch, bp.ProtectionStatus.MISSING)
    bp.apply_and_verify("owner/repo")
    assert calls == ["owner/repo"]


def test_degraded_verification_does_not_write(monkeypatch, calls) -> None:
    """`could not read` is not `is wrong`. Writing here restores the defect."""
    _verifies(monkeypatch, bp.ProtectionStatus.DEGRADED, ["403"])
    status, _ = bp.apply_and_verify("owner/repo")
    assert calls == [], "an unreadable API must not trigger a blind write"
    assert status is bp.ProtectionStatus.DEGRADED


def test_a_write_is_re_verified_so_the_verdict_reflects_reality(monkeypatch) -> None:
    """The returned status must describe the remote after the write, not before."""
    answers = iter([
        (bp.ProtectionStatus.MISSING, []),
        (bp.ProtectionStatus.ENFORCED, []),
    ])
    monkeypatch.setattr(bp, "verify_branch_protection", lambda repo: next(answers))
    monkeypatch.setattr(bp, "apply_branch_protection", lambda repo: True)
    status, _ = bp.apply_and_verify("owner/repo")
    assert status is bp.ProtectionStatus.ENFORCED
