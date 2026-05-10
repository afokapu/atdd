# URN: acc:review-phase-boundaries:D001-UNIT-002-reviewer-output-channel-bounded
# WMBT: plan/review_phase_boundaries/D001.yaml
# Harness: unit / backend

"""AC-UNIT-002: Reviewer's only output channel is ``atdd agent review
--target-commit <sha> --report-file <path>``; ``atdd agent commit`` is
rejected when persona=reviewer.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

pytestmark = [pytest.mark.platform]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def runtime_root(tmp_path: Path) -> Path:
    return tmp_path / ".atdd" / "runtime"


@pytest.fixture()
def reviewer_agent_id() -> str:
    return "reviewer-526-001"


@pytest.fixture()
def reviewer_manifest(
    runtime_root: Path, reviewer_agent_id: str,
) -> Path:
    """Write a manifest.json marking this agent as persona=reviewer."""
    agent_dir = runtime_root / "agents" / reviewer_agent_id
    agent_dir.mkdir(parents=True, exist_ok=True)
    manifest = agent_dir / "manifest.json"
    manifest.write_text(json.dumps({"persona": "reviewer", "agent_id": reviewer_agent_id}))
    return manifest


@pytest.fixture()
def coder_agent_id() -> str:
    return "coder-526-001"


@pytest.fixture()
def coder_manifest(
    runtime_root: Path, coder_agent_id: str,
) -> Path:
    """Write a manifest.json marking this agent as persona=coder."""
    agent_dir = runtime_root / "agents" / coder_agent_id
    agent_dir.mkdir(parents=True, exist_ok=True)
    manifest = agent_dir / "manifest.json"
    manifest.write_text(json.dumps({"persona": "coder", "agent_id": coder_agent_id}))
    return manifest


# ---------------------------------------------------------------------------
# Test 1: atdd agent review succeeds for reviewer persona
# ---------------------------------------------------------------------------


def test_review_succeeds_for_reviewer_persona(
    runtime_root: Path, reviewer_agent_id: str, reviewer_manifest: Path, tmp_path: Path,
):
    """``atdd agent review --target-commit <sha> --report-file <path>``
    succeeds when the agent's manifest records persona=reviewer."""
    from atdd.coach.commands import agent

    report_data = {
        "review_id": "rev-530-d001",
        "target_commit": "abcd1234",
        "reviewer_agent_id": reviewer_agent_id,
        "wmbt_urn": "wmbt:review-phase-boundaries:D001",
        "phase": "GREEN",
        "verdict": "pass",
        "tier1_risk_score": 0,
        "findings": [],
        "ac_coverage": {"acc:review-phase-boundaries:D001-UNIT-002": "covered"},
        "summary": "All checks pass.",
    }
    report = tmp_path / "report.json"
    report.write_text(json.dumps(report_data))

    path = agent.cmd_review(
        target_commit="abcd1234",
        report_file=str(report),
        agent_id=reviewer_agent_id,
        runtime_root=runtime_root,
    )
    assert path.is_file()
    payload = json.loads(path.read_text())
    assert payload["review_id"] == "rev-530-d001"


# ---------------------------------------------------------------------------
# Test 2: atdd agent commit is rejected for reviewer persona
# ---------------------------------------------------------------------------


def test_commit_rejected_for_reviewer_persona(
    runtime_root: Path, reviewer_agent_id: str, reviewer_manifest: Path,
):
    """``atdd agent commit`` is rejected with a clear error when
    persona=reviewer, citing the no-write reviewer constraint."""
    from atdd.coach.commands import agent

    with pytest.raises(ValueError, match="Reviewer.*no-write|no-write.*constraint"):
        agent.cmd_commit(
            phase="GREEN",
            message="should be rejected",
            agent_id=reviewer_agent_id,
            issue=526,
            runtime_root=runtime_root,
        )


# ---------------------------------------------------------------------------
# Test 3: atdd agent commit succeeds for coder persona
# ---------------------------------------------------------------------------


def test_commit_succeeds_for_coder_persona(
    runtime_root: Path, coder_agent_id: str, coder_manifest: Path,
):
    """``atdd agent commit`` succeeds for a non-reviewer persona (coder).
    This test validates that the guard is reviewer-specific, not blanket."""
    from atdd.coach.commands import agent

    with patch("atdd.coach.commands.agent.subprocess.run") as mock_run:
        mock_run.side_effect = [
            MagicMock(),  # git commit
            MagicMock(stdout="abc123def456\n"),  # git rev-parse HEAD
            MagicMock(stdout="feat/test\n"),  # git rev-parse --abbrev-ref HEAD (checkpoint)
        ]
        sha = agent.cmd_commit(
            phase="GREEN",
            message="test commit",
            agent_id=coder_agent_id,
            issue=526,
            runtime_root=runtime_root,
        )
    assert sha == "abc123def456"


# ---------------------------------------------------------------------------
# Test 4: commit rejection works even without manifest (no manifest = allow)
# ---------------------------------------------------------------------------


def test_commit_allowed_when_no_manifest(
    runtime_root: Path, tmp_path: Path,
):
    """When no manifest.json exists, the commit should be allowed (backward
    compatibility — agents spawned before the manifest feature was added)."""
    from atdd.coach.commands import agent

    no_manifest_id = "legacy-agent-001"
    # Intentionally do NOT create manifest.json

    with patch("atdd.coach.commands.agent.subprocess.run") as mock_run:
        mock_run.side_effect = [
            MagicMock(),  # git commit
            MagicMock(stdout="fed456abc321\n"),  # git rev-parse HEAD
            MagicMock(stdout="feat/test\n"),  # git rev-parse --abbrev-ref HEAD (checkpoint)
        ]
        sha = agent.cmd_commit(
            phase="GREEN",
            message="legacy commit",
            agent_id=no_manifest_id,
            issue=526,
            runtime_root=runtime_root,
        )
    assert sha == "fed456abc321"


# ---------------------------------------------------------------------------
# Test 5: CLI dispatcher rejects commit for reviewer via run()
# ---------------------------------------------------------------------------


def test_cli_commit_returns_nonzero_for_reviewer(
    runtime_root: Path, reviewer_agent_id: str, reviewer_manifest: Path,
):
    """The CLI ``run()`` dispatcher returns 2 when ``atdd agent commit``
    is called for a reviewer persona."""
    from atdd.coach.commands import agent

    rc = agent.run([
        "commit",
        "--phase", "GREEN",
        "--message", "blocked",
        "--agent-id", reviewer_agent_id,
    ])
    assert rc == 2
