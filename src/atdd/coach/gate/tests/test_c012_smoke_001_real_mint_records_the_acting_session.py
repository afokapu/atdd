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

Scope note, mirroring C010-SMOKE-001 — UPDATED BY #1721 (2026-08-04). This used to
read: *"neither the mint nor the check passes branch/expires_at, so tokens still
replay across branches and never expire. That consumer seam is owned by #1376 and
is deliberately not modified here."* Both call sites now pass both arguments, so
that sentence is no longer true and is not left standing — a scope note that
outlives its gap is how the gap stayed unowned in the first place (it is exactly
what C010-SMOKE-001's note did for three weeks). C010-INTEGRATION-003/004/005 own
the branch/expiry behaviour.

A SECOND SCOPE NOTE, added by #1735: the real mint also refuses an edge the issue
is not standing on, so this file seeds the issue at ``_FROM`` as well as binding a
branch to it. Both are preconditions of REACHING the attribution path, not
subjects of this acceptance — C020-INTEGRATION-001/002 own the edge precondition
itself. This file still covers the attribution path only.

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
_UID = "c012-smoke-001-real-mint-records-the-session"
_BRANCH = "feat/mint-observes-its-actor"

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


def _env(root: Path) -> dict:
    """Ambient env plus the source tree on PYTHONPATH.

    The interpreter also has a published atdd wheel installed, and a smoke that
    silently imported the released package would prove nothing about this change
    — so the source root goes first, exactly as C010-SMOKE-001 does it.
    """
    src_root = Path(__file__).resolve().parents[4]
    env = dict(os.environ)
    env["PYTHONPATH"] = str(src_root) + os.pathsep + env.get("PYTHONPATH", "")
    env["ATDD_APPROVAL_SIGNING_KEY"] = _KEY
    # Both subprocesses must resolve the SAME store the seeding below writes to, or
    # the real mint refuses twice over: for want of a branch binding (#1721) and for
    # an edge it cannot see the issue standing on (#1735). The readback then cannot
    # check the token it recorded either.
    env["ATDD_CONTROL_ROOT"] = str(root)
    # Pin BOTH sides of the observation so the run asserts the same thing on a
    # human's machine and on an agent's: a known session id, and a shell account
    # that must not end up on the token.
    env[_SESSION_ENV] = _SESSION_ID
    env["USER"] = _SHELL_ACCOUNT
    return env


def _seed_mintable_issue(root: Path) -> None:
    """Both of the mint's preconditions, in one upsert.

    #1721 requires a branch binding — the token is bound to the branch the State
    Store binds the issue to, and the mint refuses rather than writing an unbound
    one. #1735 requires the issue to be STANDING on the edge being approved. One
    `upsert` carries both: `state` is where it stands, `data["branch"]` is what the
    approval binds to.

    Written from THIS process into the same Control Root both subprocesses resolve,
    so the real command reads real state rather than being handed a value. `root` is
    made a Control Root first: the seeding runs without the ATDD_CONTROL_ROOT that is
    set only in the subprocesses' env, so resolution would otherwise walk upward and
    find the developer's real store.
    """
    from atdd.state.smoke_evidence import open_state_store

    (root / ".atdd" / "state").mkdir(parents=True, exist_ok=True)
    with open_state_store(control_root=root) as store:
        store.objects.upsert(_UID, "work_item", state=_FROM, data={"branch": _BRANCH})
        store.external_refs.link(_UID, "github", "issue", str(_ISSUE))


def test_the_real_command_mints_a_session_attributed_token(tmp_path: Path):
    env = _env(tmp_path)
    _seed_mintable_issue(tmp_path)

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
