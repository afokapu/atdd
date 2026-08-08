# URN: test:govern-lifecycle:operator-approval-token-gate:C020-SMOKE-001-the-real-command-refuses-the-edge-the-issue-is-not-on
# Acceptance: acc:govern-lifecycle:C020-SMOKE-001-the-real-command-refuses-the-edge-the-issue-is-not-on
# WMBT: wmbt:govern-lifecycle:C020
# Phase: SMOKE
# Layer: smoke
# Assertion: behavioral
"""C020-SMOKE-001 — the SHIPPED command refuses, in a real process.

Smoke, not integration: the mint is driven by a SEPARATE REAL PROCESS running the
real ``atdd coach approve`` CLI entry point — no in-process import of the command,
no monkeypatching, no fakes. The integration acceptances prove the precondition
holds on the call path; this proves it holds in the artifact an operator actually
runs.

That distinction is not academic here. Every one of the two orphan tokens that
produced #1735 was written by the real command, not by a test harness, and the
whole reason #1670 exists is that the shipped behaviour and the described
behaviour had drifted apart. C012-SMOKE-001 made the same argument for
attribution — *"the unit acceptances prove the mint path observes; this proves the
SHIPPED command does, which is the gap the 169-token corpus opened (every one of
those was minted by the real command)"*. The same sentence applies word for word
to the edge check.

The source tree goes first on PYTHONPATH because the ambient interpreter also has
a published atdd wheel installed, and a smoke that silently imported the released
package would prove nothing about this change.

Everything runs under a temp Control Root, so no live issue is touched and no
token joins the repository's real approval corpus.

RED state: the shipped command reads no issue state, so the first invocation exits
0 and writes a token for an edge the issue is nowhere near.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from atdd.coach.gate.approval import approval_relpath
from atdd.state.smoke_evidence import open_state_store

pytestmark = [pytest.mark.platform, pytest.mark.smoke]

# Never a live issue: the repo's issues are in the low thousands.
_ISSUE, _FROM, _TO = 999737, "PLANNED", "RED"
_UID = "c020-smoke-001-real-command-refuses-the-edge"
_BRANCH = "feat/mint-does-not-check-the-edge-is-reachable"


def _env(root: Path) -> dict:
    """Ambient env, the source tree first on PYTHONPATH, pinned to the temp root."""
    src_root = Path(__file__).resolve().parents[4]
    env = dict(os.environ)
    env["PYTHONPATH"] = str(src_root) + os.pathsep + env.get("PYTHONPATH", "")
    env["ATDD_APPROVAL_SIGNING_KEY"] = "smoke-operator-key"
    env["ATDD_CONTROL_ROOT"] = str(root)
    return env


def _stand_at(root: Path, phase: str) -> None:
    """Put the throwaway issue at ``phase`` in a REAL migrated store."""
    (root / ".atdd" / "state").mkdir(parents=True, exist_ok=True)
    with open_state_store(control_root=root) as store:
        store.objects.upsert(_UID, "work_item", state=phase, data={"branch": _BRANCH})
        store.external_refs.link(_UID, "github", "issue", str(_ISSUE))


def _approve(root: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "atdd.cli", "coach", "approve",
         str(_ISSUE), "--transition", f"{_FROM}->{_TO}"],
        capture_output=True, text=True, timeout=180, cwd=str(root), env=_env(root),
    )


def test_the_shipped_command_refuses_an_edge_the_issue_is_not_standing_on(tmp_path: Path):
    """The #1726 reproduction, against the binary an operator actually invokes."""
    _stand_at(tmp_path, "INIT")

    refused = _approve(tmp_path)

    assert refused.returncode != 0, (
        f"the SHIPPED command minted for {_FROM}->{_TO} while the issue was at INIT; "
        f"stdout:\n{refused.stdout[-800:]}"
    )
    # The refusal has to be actionable in the artifact too, not only in the tests.
    assert "INIT" in refused.stdout + refused.stderr, (
        f"the shipped refusal does not name the phase the issue is on; "
        f"stdout:\n{refused.stdout[-800:]}"
    )
    # And it must leave nothing consumable behind.
    assert not (tmp_path / approval_relpath(_ISSUE, _FROM, _TO)).exists(), (
        "the shipped command refused and still wrote the token"
    )


def test_the_shipped_command_still_mints_the_edge_the_issue_reaches(tmp_path: Path):
    """The negative control, in the same real process.

    Without this the file above would be satisfied by a command that refused
    everything — including every legitimate approval an operator will ever make.
    """
    _stand_at(tmp_path, "INIT")
    assert _approve(tmp_path).returncode != 0

    # The work proceeds and the issue genuinely arrives at PLANNED.
    _stand_at(tmp_path, _FROM)

    approved = _approve(tmp_path)

    assert approved.returncode == 0, (
        f"the shipped command refused the edge the issue was standing on; "
        f"stdout:\n{approved.stdout[-800:]}\nstderr:\n{approved.stderr[-800:]}"
    )
    assert (tmp_path / approval_relpath(_ISSUE, _FROM, _TO)).exists(), (
        f"the shipped command reported success and wrote no token; "
        f"stdout:\n{approved.stdout[-800:]}"
    )
