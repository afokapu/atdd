# URN: test:spawn-agents:atdd-spawn-skeleton-and-harness:E004-UNIT-001-launch-intent-payload-rejected
# Acceptance: acc:spawn-agents:E004-UNIT-001-launch-intent-payload-rejected
# WMBT: wmbt:spawn-agents:E004
# Phase: RED
# Layer: application
"""E004-UNIT-001 — the ``atdd-cmux-send`` shim's pre-send classifier flags a
launch-intent ``claude`` payload, exits with code 2, and prints an educational
error pointing the operator at ``atdd spawn --worktree``. The real ``cmux send``
binary is NEVER invoked for a rejected payload — rejection happens pre-send.

Issue #662 — raw ``cmux send <surface> "claude ..."`` silently binds the
pane's incidental shell cwd (usually the workspace root, NOT the issue
worktree). The shim rejects those launches at the source so the operator is
pushed toward the cwd-correct ``atdd spawn`` path.

Public contract exercised by this RED suite (to be implemented in
``src/atdd/coach/wrappers/atdd_cmux_send.py``):

  * ``is_launch_intent(payload: str) -> bool`` — the pre-send classifier.
  * ``main(argv, *, cmux_send=None) -> int`` — CLI entry. ``cmux_send`` is an
    injectable forwarder ``(surface, payload) -> int`` (the real ``cmux send``
    subprocess when ``None``); positional argv is ``[<surface>, <payload>]``.
"""
from __future__ import annotations

import pytest

# --------------------------------------------------------------------------
# Curated true-positive corpus — ≥10 launch-intent payloads. Each begins
# (after optional leading whitespace) with ``claude`` followed by a space or
# newline: the documented launch-intent shapes ``^claude ``, ``claude\n``,
# ``claude --``.
# --------------------------------------------------------------------------
LAUNCH_INTENT_PAYLOADS = [
    "claude ",
    "claude\n",
    "claude --permission-mode acceptEdits",
    'claude --dangerously-skip-permissions "$(cat p.md)"',
    "claude -p 'fix the failing test'",
    "claude --model claude-opus-4-7 --permission-mode acceptEdits",
    "claude --resume",
    "claude --continue\n",
    "claude --add-dir /tmp/wt",
    "claude   --verbose",
    "  claude --permission-mode plan",
]


class FakeCmuxSend:
    """Stands in for the real ``cmux send`` binary. Records every forwarded
    ``(surface, payload)`` so a test can assert that a rejected payload was
    NEVER forwarded (rejection is pre-send)."""

    def __init__(self, returncode: int = 0) -> None:
        self.calls: list[tuple[str, str]] = []
        self._returncode = returncode

    def __call__(self, surface: str, payload: str) -> int:
        self.calls.append((surface, payload))
        return self._returncode

    @property
    def invoked(self) -> bool:
        return bool(self.calls)


def _shim():
    """Import inside the test so collection succeeds before the module exists."""
    from atdd.coach.wrappers import atdd_cmux_send

    return atdd_cmux_send


def test_corpus_has_at_least_ten_true_positives():
    assert len(LAUNCH_INTENT_PAYLOADS) >= 10


@pytest.mark.parametrize("payload", LAUNCH_INTENT_PAYLOADS)
def test_launch_intent_payload_is_classified(payload):
    assert _shim().is_launch_intent(payload) is True


def test_every_true_positive_flagged_at_least_ten_of_ten():
    shim = _shim()
    flagged = [p for p in LAUNCH_INTENT_PAYLOADS if shim.is_launch_intent(p)]
    assert len(flagged) >= 10


@pytest.mark.parametrize("payload", LAUNCH_INTENT_PAYLOADS)
def test_launch_intent_payload_rejected_with_exit_2(payload):
    shim = _shim()
    fake = FakeCmuxSend()
    rc = shim.main(["surface-1", payload], cmux_send=fake)
    assert rc == 2


@pytest.mark.parametrize("payload", LAUNCH_INTENT_PAYLOADS)
def test_rejected_payload_is_never_forwarded_to_cmux(payload):
    """Rejection happens pre-send: the fake ``cmux send`` is never invoked."""
    shim = _shim()
    fake = FakeCmuxSend()
    shim.main(["surface-1", payload], cmux_send=fake)
    assert fake.invoked is False


def test_rejection_stderr_is_educational_and_copy_pasteable(capsys):
    shim = _shim()
    fake = FakeCmuxSend()
    shim.main(["surface-1", "claude --permission-mode acceptEdits"], cmux_send=fake)
    err = capsys.readouterr().err
    # The error must name the correct CLI with a copy-pasteable command.
    assert "atdd spawn --worktree" in err
