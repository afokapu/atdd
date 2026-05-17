# URN: test:spawn-agents:atdd-spawn-skeleton-and-harness:E004-UNIT-002-non-launch-payload-passthrough
# Acceptance: acc:spawn-agents:E004-UNIT-002-non-launch-payload-passthrough
# WMBT: wmbt:spawn-agents:E004
# Phase: RED
# Layer: application
"""E004-UNIT-002 — non-launch payloads, including incidental ``claude``
mentions (``claude.json``, ``claude_code``, prose), pass the classifier and
are forwarded to the real ``cmux send`` with surface + payload argv unchanged.

Issue #662 — the classifier must reject launch intent WITHOUT false-positiving
on the many benign payloads that merely contain the substring ``claude``;
otherwise the shim breaks ``cmux send`` for everyday operator use.
"""
from __future__ import annotations

import pytest

# --------------------------------------------------------------------------
# Curated true-negative corpus — ≥10 non-launch payloads. Several contain the
# substring ``claude`` incidentally (filename, identifier, prose, the
# ``claude-code`` adapter name, a URL) and MUST NOT be flagged.
# --------------------------------------------------------------------------
NON_LAUNCH_PAYLOADS = [
    "ls -la",
    "cat claude.json",
    "grep claude_code src/",
    'echo "ask Claude about it"',
    'git commit -m "mention claude"',
    "python claude_helper.py",
    "claudemon --status",
    "atdd spawn --persona coder --llm claude-code --worktree /x --issue 1 --agent-id a-1 --runtime /r",
    "# launch claude here later",
    "open https://claude.ai/code",
    "vim claude/config.yaml",
]


class FakeCmuxSend:
    """Records forwarded ``(surface, payload)`` so a test can assert that a
    safe payload reaches the real ``cmux send`` argv-unchanged."""

    def __init__(self, returncode: int = 0) -> None:
        self.calls: list[tuple[str, str]] = []
        self._returncode = returncode

    def __call__(self, surface: str, payload: str) -> int:
        self.calls.append((surface, payload))
        return self._returncode


def _shim():
    from atdd.coach.wrappers import atdd_cmux_send

    return atdd_cmux_send


def test_corpus_has_at_least_ten_true_negatives():
    assert len(NON_LAUNCH_PAYLOADS) >= 10


@pytest.mark.parametrize("payload", NON_LAUNCH_PAYLOADS)
def test_non_launch_payload_is_classified_safe(payload):
    assert _shim().is_launch_intent(payload) is False


def test_zero_false_positives_across_corpus():
    shim = _shim()
    false_positives = [p for p in NON_LAUNCH_PAYLOADS if shim.is_launch_intent(p)]
    assert false_positives == []


@pytest.mark.parametrize("payload", NON_LAUNCH_PAYLOADS)
def test_non_launch_payload_exits_zero(payload):
    shim = _shim()
    fake = FakeCmuxSend()
    rc = shim.main(["surface-7", payload], cmux_send=fake)
    assert rc == 0


@pytest.mark.parametrize("payload", NON_LAUNCH_PAYLOADS)
def test_non_launch_payload_forwarded_unchanged(payload):
    """The shim forwards the surface and payload argv to ``cmux send`` exactly
    as received — no rewriting, no autocorrect."""
    shim = _shim()
    fake = FakeCmuxSend()
    shim.main(["surface-7", payload], cmux_send=fake)
    assert fake.calls == [("surface-7", payload)]
