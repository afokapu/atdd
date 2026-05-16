# URN: test:spawn-agents:atdd-spawn-skeleton-and-harness:E004-UNIT-003-escape-flag-bypasses-classifier
# Acceptance: acc:spawn-agents:E004-UNIT-003-escape-flag-bypasses-classifier
# WMBT: wmbt:spawn-agents:E004
# Phase: RED
# Layer: application
"""E004-UNIT-003 — the ``--i-know-what-im-doing`` escape flag bypasses the
pre-send classifier so test scaffolding (and a knowing operator) can exercise
the otherwise-rejected launch path.

Issue #662 — the shim itself must be testable end-to-end; the escape flag is
the seam. With it set, a launch-intent payload is forwarded to ``cmux send``
unchanged, the shim exits 0, and NO educational rejection is printed.
"""
from __future__ import annotations


class FakeCmuxSend:
    """Records forwarded ``(surface, payload)``."""

    def __init__(self, returncode: int = 0) -> None:
        self.calls: list[tuple[str, str]] = []
        self._returncode = returncode

    def __call__(self, surface: str, payload: str) -> int:
        self.calls.append((surface, payload))
        return self._returncode


def _shim():
    from atdd.coach.wrappers import atdd_cmux_send

    return atdd_cmux_send


def test_escape_flag_payload_would_otherwise_be_rejected():
    """Sanity anchor: without the flag this payload IS launch intent."""
    assert _shim().is_launch_intent("claude --permission-mode acceptEdits") is True


def test_escape_flag_exits_zero_despite_launch_intent_payload():
    shim = _shim()
    fake = FakeCmuxSend()
    rc = shim.main(
        ["--i-know-what-im-doing", "surface-3", "claude --permission-mode acceptEdits"],
        cmux_send=fake,
    )
    assert rc == 0


def test_escape_flag_forwards_payload_unchanged():
    shim = _shim()
    fake = FakeCmuxSend()
    shim.main(
        ["--i-know-what-im-doing", "surface-3", "claude --permission-mode acceptEdits"],
        cmux_send=fake,
    )
    assert fake.calls == [("surface-3", "claude --permission-mode acceptEdits")]


def test_escape_flag_prints_no_educational_rejection(capsys):
    shim = _shim()
    fake = FakeCmuxSend()
    shim.main(
        ["--i-know-what-im-doing", "surface-3", "claude --permission-mode acceptEdits"],
        cmux_send=fake,
    )
    err = capsys.readouterr().err
    assert "atdd spawn --worktree" not in err
