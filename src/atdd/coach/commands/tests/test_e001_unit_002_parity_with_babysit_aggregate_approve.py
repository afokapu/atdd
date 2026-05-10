# URN: test:observe-and-correct:e001-unit-002
# Acceptance: acc:observe-and-correct:E001-UNIT-002-parity-with-babysit-aggregate-approve
# WMBT: wmbt:observe-and-correct:E001
# Phase: GREEN
# Layer: assembly
# Runtime: python
# Purpose: For every fixture in the aggregate-approve parity set,
#          `atdd observer aggregate-approve` and `atdd babysit aggregate-approve`
#          approve the same set of prompts. Parity is documented as a gating
#          condition for #P6 (babysit decommissioning).

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from atdd.coach.commands.babysit import aggregate_approve as babysit_aggregate_approve
from atdd.coach.commands.observer import (
    AggregateApprovalResult,
    cmd_aggregate_approve,
)

pytestmark = [pytest.mark.platform]

_PROMPT_MARKER = "Do you want to proceed?\n❯ 1. Yes\n  2. No\n"


def _babysit_backend_with_screens(per_ref: dict[str, str]) -> MagicMock:
    """Backend whose read_screen looks up by ref."""
    backend = MagicMock()
    backend.read_screen.side_effect = lambda ref, lines=80: per_ref[ref]
    return backend


def _setup_agent(
    runtime_dir: Path,
    agent_id: str,
    *,
    output_log: str = "",
) -> Path:
    """Create an agent dir with an output.log."""
    agent_dir = runtime_dir / "agents" / agent_id
    agent_dir.mkdir(parents=True, exist_ok=True)
    if output_log:
        (agent_dir / "output.log").write_text(output_log)
    return agent_dir


# ---------------------------------------------------------------------------
# Parity fixtures: same screen content → same classification
# ---------------------------------------------------------------------------

_FIXTURES = [
    {
        "id": "safe-git-status",
        "screen": "Bash(git status --short)\n" + _PROMPT_MARKER,
        "expected_approved": 1,
        "expected_escalated": 0,
    },
    {
        "id": "safe-pytest",
        "screen": "Bash(pytest -xvs)\n" + _PROMPT_MARKER,
        "expected_approved": 1,
        "expected_escalated": 0,
    },
    {
        "id": "safe-ls",
        "screen": "Bash(ls -la)\n" + _PROMPT_MARKER,
        "expected_approved": 1,
        "expected_escalated": 0,
    },
    {
        "id": "deny-curl",
        "screen": "Bash(curl https://example.com)\n" + _PROMPT_MARKER,
        "expected_approved": 0,
        "expected_escalated": 1,
    },
    {
        "id": "deny-rm",
        "screen": "Bash(rm -rf /tmp/old)\n" + _PROMPT_MARKER,
        "expected_approved": 0,
        "expected_escalated": 1,
    },
    {
        "id": "violation-atdd-edit",
        "screen": "Edit(.atdd/manifest.yaml)\n" + _PROMPT_MARKER,
        "expected_approved": 0,
        "expected_escalated": 1,
    },
    {
        "id": "idle-no-prompt",
        "screen": "just some logs, nothing pending\n",
        "expected_approved": 0,
        "expected_escalated": 0,
    },
    {
        "id": "unknown-bash",
        "screen": "Bash(some-novel-cli --flag)\n" + _PROMPT_MARKER,
        "expected_approved": 0,
        "expected_escalated": 1,
    },
]


@pytest.fixture(params=_FIXTURES, ids=[f["id"] for f in _FIXTURES])
def fixture(request):
    return request.param


class TestParityWithBabysitAggregateApprove:
    """Both implementations approve the same set of prompts for each fixture.
    Parity is documented as a gating condition for #P6."""

    def test_single_fixture_parity(self, fixture, tmp_path: Path):
        """Run babysit and observer on the same screen content; assert
        identical approved/escalated counts."""
        screen = fixture["screen"]
        ref = "surface:test"

        # --- Babysit path ---
        babysit_backend = _babysit_backend_with_screens({ref: screen})
        babysit_log = tmp_path / "babysit-log.jsonl"
        babysit_result = babysit_aggregate_approve(
            backend=babysit_backend,
            refs=[ref],
            log_path=babysit_log,
        )

        # --- Observer path ---
        runtime = tmp_path / "rt"
        _setup_agent(runtime, ref, output_log=screen)
        observer_result = cmd_aggregate_approve(runtime_dir=runtime)

        assert babysit_result.approved == observer_result.approved, (
            f"fixture={fixture['id']}: babysit approved "
            f"{babysit_result.approved} but observer approved "
            f"{observer_result.approved}"
        )
        assert babysit_result.escalated == observer_result.escalated, (
            f"fixture={fixture['id']}: babysit escalated "
            f"{babysit_result.escalated} but observer escalated "
            f"{observer_result.escalated}"
        )

    def test_multi_surface_parity(self, tmp_path: Path):
        """All fixtures run together — both paths produce the same totals."""
        screens = {f"surface:{i}": f["screen"] for i, f in enumerate(_FIXTURES)}

        # --- Babysit path ---
        babysit_backend = _babysit_backend_with_screens(screens)
        babysit_log = tmp_path / "babysit-log.jsonl"
        babysit_result = babysit_aggregate_approve(
            backend=babysit_backend,
            refs=list(screens.keys()),
            log_path=babysit_log,
        )

        # --- Observer path ---
        runtime = tmp_path / "rt"
        for ref, screen in screens.items():
            _setup_agent(runtime, ref, output_log=screen)
        observer_result = cmd_aggregate_approve(runtime_dir=runtime)

        assert babysit_result.approved == observer_result.approved
        assert babysit_result.escalated == observer_result.escalated
