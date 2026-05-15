"""Regression: a transient cmux/tmux IPC failure must not abort the coach.

#715 — `cmux new-pane` occasionally fails with a broken-pipe / socket-write
error. With the default retry budget (`max_retries=0`) the coach used to abort
the whole run on the first such hiccup. Transient IPC errors now get extra
retries, free of `max_retries`, while genuine spawn failures still fail fast.
"""

from pathlib import Path

import pytest

from atdd.coach.handlers import spawn
from atdd.coach.handlers.spawn import _is_transient_spawn_error, _spawn_with_retries
from atdd.coach.handlers.state_machine import CoachContext


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    """Collapse backoff so the retry tests stay fast."""
    monkeypatch.setattr(spawn.time, "sleep", lambda *_: None)


def _ctx(max_retries):
    return CoachContext(issue_number=715, max_retries=max_retries)


def _run(ctx, base_agent_id="coder-715-x", tmp=Path("/tmp")):
    return _spawn_with_retries(
        ctx, None, "coder", "GREEN", "claude",
        "persona-prompt", tmp, base_agent_id, tmp,
    )


def _spawn_stub(behaviours):
    """Build a `_call_spawn` replacement: each call pops the next behaviour
    (an exception to raise, or a dict to return). Records its call count."""
    calls = []

    def fake(*_args, **_kwargs):
        calls.append(1)
        item = behaviours[len(calls) - 1]
        if isinstance(item, BaseException):
            raise item
        return item

    fake.count = lambda: len(calls)
    return fake


def test_is_transient_spawn_error_classifies():
    assert _is_transient_spawn_error(RuntimeError("cmux new-pane failed: Broken pipe"))
    assert _is_transient_spawn_error(OSError("Failed to write to socket"))
    assert _is_transient_spawn_error(OSError("[Errno 32] Broken pipe"))
    assert _is_transient_spawn_error(RuntimeError("Connection reset by peer"))
    # genuine, deterministic failures are NOT transient
    assert not _is_transient_spawn_error(RuntimeError("missing worktree"))
    assert not _is_transient_spawn_error(ValueError("malformed persona prompt"))


def test_transient_error_retried_free_of_default_budget(monkeypatch):
    """The core #715 fix: with max_retries=0, a transient cmux error is still
    retried — it does not abort the coach."""
    success = {"agent_id": "coder-715-x"}
    stub = _spawn_stub([
        RuntimeError("cmux new-pane failed (exit 1): Failed to write to socket (Broken pipe)"),
        RuntimeError("cmux new-pane failed (exit 1): Broken pipe"),
        success,
    ])
    monkeypatch.setattr(spawn, "_call_spawn", stub)

    result = _run(_ctx(max_retries=0))

    assert result == success
    assert stub.count() == 3  # 1 initial + 2 transient retries, then success


def test_genuine_error_fails_fast_at_default_budget(monkeypatch):
    """Behaviour unchanged for genuine failures: max_retries=0 → 1 attempt,
    no retry. Real bugs surface immediately instead of hiding behind retries."""
    stub = _spawn_stub([RuntimeError("missing worktree")] * 8)
    monkeypatch.setattr(spawn, "_call_spawn", stub)

    result = _run(_ctx(max_retries=0))

    assert result is None
    assert stub.count() == 1


def test_transient_retries_are_bounded(monkeypatch):
    """A permanently broken cmux socket cannot loop forever — transient
    retries are capped, then the coach gives up."""
    stub = _spawn_stub([RuntimeError("Broken pipe")] * 20)
    monkeypatch.setattr(spawn, "_call_spawn", stub)

    result = _run(_ctx(max_retries=0))

    assert result is None
    # 1 initial attempt + _MAX_TRANSIENT_SPAWN_RETRIES extra
    assert stub.count() == 1 + spawn._MAX_TRANSIENT_SPAWN_RETRIES


def test_genuine_error_still_honours_explicit_max_retries(monkeypatch):
    """An operator-set --max-retries continues to apply to genuine failures."""
    stub = _spawn_stub([RuntimeError("missing worktree")] * 8)
    monkeypatch.setattr(spawn, "_call_spawn", stub)

    result = _run(_ctx(max_retries=2))

    assert result is None
    assert stub.count() == 3  # max_retries + 1
