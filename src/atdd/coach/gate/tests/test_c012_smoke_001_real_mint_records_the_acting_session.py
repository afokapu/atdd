# URN: test:govern-lifecycle:operator-approval-token-gate:C012-SMOKE-001-real-mint-records-the-acting-session
# Acceptance: acc:govern-lifecycle:C012-SMOKE-001-real-mint-records-the-acting-session
# WMBT: wmbt:govern-lifecycle:C012
# Phase: SMOKE
# Layer: smoke
# Assertion: behavioral
"""C012-SMOKE-001 — the real ``atdd coach approve`` records the session that ran it.

Smoke, not unit: the token is minted by a SEPARATE REAL PROCESS running the real
``atdd coach approve`` CLI entry point, and read back by a second real process
through the real ``ApprovalTokenGateCheck`` — no in-process import of the mint or
the check, no monkeypatching, no fakes. The unit acceptances prove the mint path
observes; this proves the SHIPPED command does, which is the gap the 169-token
corpus opened (every one of those was minted by the real command).

The token is written under a temp root, so the repository's own approval corpus
is never touched and no 170th token joins the population this issue counts.

Scope note, mirroring C010-SMOKE-001: neither the mint nor the check passes
``branch``/``expires_at``, so tokens still replay across branches and never
expire. That consumer seam is owned by #1376 and is deliberately not modified
here; this smoke covers the attribution path it can honestly reach.

RED state: the real command records ``$USER`` and writes no ``agent_session``,
so the assertions on the minted token fail.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]

_ISSUE, _FROM, _TO = 1718, "INIT", "PLANNED"
_PRE_FIX_ISSUE = 1017
_SESSION_ENV = "CLAUDE_CODE_SESSION_ID"
_SESSION_ID = "smoke-c012-0000-1111-2222-333344445555"
_SHELL_ACCOUNT = "a-human-who-did-not-approve-this"
_KEY = "smoke-operator-key"

# Runs in a fresh interpreter AFTER the real mint: reads the real token off disk
# through the real gate check, then mints a pre-fix-shaped token (the field set
# measured across all 169 live tokens) and reads that back the same way.
_READBACK = """
import json, sys
from pathlib import Path
from atdd.coach.gate.approval import sign_approval
from atdd.coach.gate.approval_check import ApprovalTokenGateCheck
from atdd.coach.gate.approval_paths import approval_token_path
from atdd.coach.gate.decision import GateContext

root = Path(sys.argv[1])
issue, from_phase, to_phase = int(sys.argv[2]), sys.argv[3], sys.argv[4]
pre_fix_issue, key = int(sys.argv[5]), sys.argv[6]

check = ApprovalTokenGateCheck(signing_key=key)
minted = check.run(GateContext(
    issue_number=issue, from_phase=from_phase, to_phase=to_phase, worktree=root))

# A token from the old regime: the exact field set the corpus carries, nothing
# else. Written at the CANONICAL location (#1376), so this exercises the
# schema-version distinction rather than the worktree-local back-compat fallback.
pre_fix_path = approval_token_path(root, pre_fix_issue, from_phase, to_phase)
pre_fix_path.parent.mkdir(parents=True, exist_ok=True)
pre_fix_path.write_text(json.dumps({
    "issue": pre_fix_issue,
    "from_phase": from_phase,
    "to_phase": to_phase,
    "approved_by": "alecfokapu",
    "approved_at": "2026-07-01T00:00:00+00:00",
    "signature": sign_approval(pre_fix_issue, from_phase, to_phase, key),
}))
pre_fix = check.run(GateContext(
    issue_number=pre_fix_issue, from_phase=from_phase, to_phase=to_phase, worktree=root))

print(json.dumps({
    "minted_passed": minted.passed, "minted_message": minted.message,
    "pre_fix_passed": pre_fix.passed, "pre_fix_message": pre_fix.message,
}))
"""


def _env() -> dict:
    """Ambient env plus the source tree on PYTHONPATH.

    The interpreter also has a published atdd wheel installed, and a smoke that
    silently imported the released package would prove nothing about this change
    — so the source root goes first, exactly as C010-SMOKE-001 does it.
    """
    src_root = Path(__file__).resolve().parents[4]
    env = dict(os.environ)
    env["PYTHONPATH"] = str(src_root) + os.pathsep + env.get("PYTHONPATH", "")
    env["ATDD_APPROVAL_SIGNING_KEY"] = _KEY
    # Pin BOTH sides of the observation so the run asserts the same thing on a
    # human's machine and on an agent's: a known session id, and a shell account
    # that must not end up on the token.
    env[_SESSION_ENV] = _SESSION_ID
    env["USER"] = _SHELL_ACCOUNT
    return env


def test_the_real_command_mints_a_session_attributed_token(tmp_path: Path):
    env = _env()

    minted = subprocess.run(
        [sys.executable, "-m", "atdd.cli", "coach", "approve",
         str(_ISSUE), "--transition", f"{_FROM}->{_TO}"],
        capture_output=True, text=True, timeout=180, cwd=str(tmp_path), env=env,
    )
    assert minted.returncode == 0, (
        f"the real mint failed (rc={minted.returncode}); stderr:\n{minted.stderr[:800]}"
    )

    # WHERE the token goes is #1376's Control-Root resolution, not this test's
    # assumption — hardcoding the pre-#1376 worktree-local path here would pass
    # today only because resolve_operational_root degrades to the worktree in a
    # bare tmp dir, and would silently stop covering the real location the moment
    # it does not. Take the path from what the real command reports writing.
    token_path = Path(minted.stdout.strip().splitlines()[-1].rsplit(": ", 1)[-1])
    assert token_path.exists(), (
        f"the real command reported writing {token_path}, which does not exist; "
        f"stdout:\n{minted.stdout[-800:]}"
    )
    token = json.loads(token_path.read_text())

    # The shipped artifact names WHICH session produced it...
    assert token.get("agent_session") == {
        "provider": "claude", "session_id": _SESSION_ID
    }, f"the real token records {token.get('agent_session')!r}"
    # ...and does not credit the account whose shell it ran in.
    assert _SHELL_ACCOUNT not in json.dumps(token), (
        f"the real mint recorded the shell account on the token: {token!r}"
    )

    readback = subprocess.run(
        [sys.executable, "-c", _READBACK, str(tmp_path), str(_ISSUE), _FROM, _TO,
         str(_PRE_FIX_ISSUE), _KEY],
        capture_output=True, text=True, timeout=180, cwd=str(tmp_path), env=env,
    )
    assert readback.returncode == 0, (
        f"the real readback failed (rc={readback.returncode}); "
        f"stderr:\n{readback.stderr[:800]}"
    )
    result = json.loads(readback.stdout.strip().splitlines()[-1])

    # The real gate consumer accepts the real token and says what produced it.
    assert result["minted_passed"] is True, result["minted_message"]
    assert _SESSION_ID in result["minted_message"]

    # And it reads a token from the old regime as unattributed rather than as an
    # operator approval — the two regimes are distinguishable through the shipped
    # read path, which is the whole point of the version stamp.
    assert result["pre_fix_passed"] is True, (
        "a pre-fix token must still open its own transition; versioning the schema "
        "is not a migration"
    )
    assert "unattributed" in result["pre_fix_message"].lower(), (
        f"the shipped read path reports a pre-fix token as "
        f"{result['pre_fix_message']!r}"
    )
