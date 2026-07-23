# URN: test:govern-lifecycle:operator-approval-token-gate:C010-SMOKE-001-real-token-does-not-replay-across-checkouts
# Acceptance: acc:govern-lifecycle:C010-SMOKE-001-real-token-does-not-replay-across-checkouts
# WMBT: wmbt:govern-lifecycle:C010
# Phase: SMOKE
# Layer: smoke
# Assertion: behavioral
"""C010-SMOKE-001 — the real signing path refuses a cross-branch token.

Smoke, not unit: the token is minted and verified in a SEPARATE REAL PROCESS
against the real installed package — no in-process import of the module under
test, no monkeypatching, no fakes. This proves the replay property is closed in
the shipped artifact rather than only in the test tree, which is exactly the
gap the live 19-of-19 reproduction exposed.

Scope note: refusing a cross-branch token at the TRANSITION gate additionally
requires the gate consumer to pass the current branch into verify_token. That
consumer is the approval-token path seam owned by #1376 and is deliberately NOT
modified here, so this smoke covers the signing/verification path it can honestly
reach.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]

# Runs in a fresh interpreter: mint for feat/alpha, verify on both branches.
_PROGRAM = """
from atdd.coach.gate.approval import build_token, verify_token
import json

KEY = "operator-secret-key"
token = build_token(
    1525, "PLANNED", "RED",
    approved_by="operator", approved_at="2026-07-22T00:00:00Z",
    branch="feat/alpha", expires_at="2099-01-01T00:00:00Z", key=KEY,
)
print(json.dumps({
    "own_branch": verify_token(token, 1525, "PLANNED", "RED", branch="feat/alpha", key=KEY),
    "other_branch": verify_token(token, 1525, "PLANNED", "RED", branch="feat/beta", key=KEY),
    "token_has_branch": token.get("branch"),
}))
"""


def test_real_operator_signed_token_does_not_verify_on_another_branch(tmp_path):
    """A real subprocess proves the shipped path binds the branch."""
    # Exercise the SOURCE UNDER TEST in a real separate process. PYTHONPATH is set
    # explicitly (rather than relying on cwd) because the ambient interpreter also
    # has a published atdd wheel installed, and a smoke that silently imported the
    # released package would prove nothing about this change.
    src_root = Path(__file__).resolve().parents[4]
    env = dict(os.environ)
    env["PYTHONPATH"] = str(src_root) + os.pathsep + env.get("PYTHONPATH", "")

    proc = subprocess.run(
        [sys.executable, "-c", _PROGRAM],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=str(tmp_path),  # outside the source tree; imports come from PYTHONPATH
        env=env,
    )
    assert proc.returncode == 0, (
        f"real subprocess failed (rc={proc.returncode}); stderr:\n{proc.stderr[:800]}"
    )

    result = json.loads(proc.stdout.strip().splitlines()[-1])

    # The guard discriminates rather than refusing everything...
    assert result["own_branch"] is True, (
        "the token must still verify on the branch it was signed for"
    )
    # ...and the replay across branches is closed in the shipped artifact.
    assert result["other_branch"] is False, (
        "a token minted for feat/alpha verified on feat/beta in a real process — "
        "the replay-across-branch property is NOT closed in the shipped package"
    )
    assert result["token_has_branch"] == "feat/alpha"
