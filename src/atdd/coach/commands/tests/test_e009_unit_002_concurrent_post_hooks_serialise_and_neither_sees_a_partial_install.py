# URN: test:integration-hardening:run-upgrade-unattended:E009-UNIT-002-concurrent-post-hooks-serialise-and-neither-sees-a-partial-install
# Acceptance: acc:integration-hardening:E009-UNIT-002-concurrent-post-hooks-serialise-and-neither-sees-a-partial-install
# WMBT: wmbt:integration-hardening:E009
# Phase: RED
# Layer: application
# Runtime: python
# Assertion: behavioral
"""E009-UNIT-002 — sixty worktrees pull all day; two that pull at once must not both install.

RED Test for acc:integration-hardening:E009-UNIT-002-concurrent-post-hooks-serialise-and-neither-sees-a-partial-install
wagon: integration-hardening | feature: run-upgrade-unattended | phase: RED
WMBT: wmbt:integration-hardening:E009

E008 already built the install-scoped lock and proved it serialises ``atdd
upgrade``. What #1762 changes is the *posture* toward contention. E008 waits up
to :data:`UPGRADE_LOCK_TIMEOUT` (300 s) because an operator is watching a command
they ran. A post-merge hook has no such licence: a contended lock there means a
sibling worktree is already performing this very upgrade on our behalf, so
waiting would freeze a human's terminal after a pull in order to duplicate work
already in flight. The self-upgrade therefore *tries* the lock and stands down.

The serialisation guarantee is untouched by that, because it comes from the lock
and not from the wait — which is exactly what the first test here checks.

Nothing about the locking path is patched: these use the real ``flock``.
"""
from __future__ import annotations

import io
import threading
import time
from unittest.mock import patch

import pytest

import atdd.coach.commands.upgrader as upgrader

pytestmark = [pytest.mark.coach, pytest.mark.platform]


def upgrade_held():
    """The real install lock, held by a live holder for the duration of a ``with``."""
    return upgrader.upgrade_lock()


def test_e009_unit_002_only_one_of_two_concurrent_hooks_installs():
    """Two post-hooks firing at the same instant: exactly one enters the install.

    Both threads are released from a barrier so they genuinely race, and the
    patched upgrade is slow enough that an unserialised pair would overlap.
    """
    entries: list[tuple[float, float]] = []
    entries_lock = threading.Lock()
    barrier = threading.Barrier(2)

    def slow_upgrade():
        started = time.monotonic()
        time.sleep(0.4)
        with entries_lock:
            entries.append((started, time.monotonic()))
        return True, ""

    outcomes: list[str] = []
    outcomes_lock = threading.Lock()

    def worker():
        barrier.wait()
        result = upgrader.self_upgrade(stream=io.StringIO())
        with outcomes_lock:
            outcomes.append(result)

    with patch.object(upgrader, "_resolve_latest_version", return_value="9.9.9"), \
         patch.object(upgrader, "_gate_version", return_value="4.0.0"), \
         patch.object(upgrader, "auto_upgrade", side_effect=slow_upgrade):
        threads = [threading.Thread(target=worker) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

    assert all(not t.is_alive() for t in threads), "a concurrent self-upgrade hung"
    assert len(entries) == 1, (
        f"exactly one of the two runs may rewrite the shared install; {len(entries)} did"
    )
    assert sorted(outcomes) == [upgrader.SELF_UPGRADE_CONTENDED, upgrader.SELF_UPGRADE_UPGRADED], (
        f"expected one upgrade and one stand-down, got {outcomes}"
    )


def test_e009_unit_002_the_loser_stands_down_instead_of_waiting_out_the_timeout():
    """A held lock is declined promptly, not waited on for E008's 300 seconds."""
    stream = io.StringIO()

    with upgrade_held():
        with patch.object(upgrader, "_resolve_latest_version", return_value="9.9.9"), \
             patch.object(upgrader, "_gate_version", return_value="4.0.0"), \
             patch.object(upgrader, "auto_upgrade") as never:
            started = time.monotonic()
            outcome = upgrader.self_upgrade(stream=stream)
            elapsed = time.monotonic() - started

    assert outcome == upgrader.SELF_UPGRADE_CONTENDED
    never.assert_not_called()
    assert elapsed < 5.0, (
        f"the hook waited {elapsed:.1f}s on a contended lock; a post-merge hook must "
        f"stand down, not stall the terminal for up to {upgrader.UPGRADE_LOCK_TIMEOUT}s"
    )
    assert "lock" in stream.getvalue() and "unaffected" in stream.getvalue(), (
        f"the stand-down must name the reason and reassure; got:\n{stream.getvalue()}"
    )


def test_e009_unit_002_a_run_that_arrives_after_the_upgrade_finds_nothing_left_to_do():
    """The re-read inside the lock: no second pip run over an already-current install.

    This is the sequential companion to the race above — the arrival order that
    actually dominates in the field, where the sixty agents that pull *after* the
    winner has finished must each cost one check and nothing more.
    """
    installed = {"version": "4.0.0"}

    def upgrade_and_advance():
        installed["version"] = "9.9.9"
        return True, ""

    with patch.object(upgrader, "_resolve_latest_version", return_value="9.9.9"), \
         patch.object(upgrader, "_gate_version", side_effect=lambda: installed["version"]), \
         patch.object(upgrader, "auto_upgrade", side_effect=upgrade_and_advance) as once:
        first = upgrader.self_upgrade(stream=io.StringIO())
        second = upgrader.self_upgrade(stream=io.StringIO())
        third = upgrader.self_upgrade(stream=io.StringIO())

    assert first == upgrader.SELF_UPGRADE_UPGRADED
    assert second == upgrader.SELF_UPGRADE_DECLINED
    assert third == upgrader.SELF_UPGRADE_DECLINED, "the sequence must converge, not oscillate"
    assert once.call_count == 1, (
        f"one version delta must produce one mutation; auto_upgrade ran {once.call_count} times"
    )


def test_e009_unit_002_no_environment_variable_skips_the_lock():
    """The stand-down has no bypass. E030 retired that class and #1762 adds none.

    The only variable the self-upgrade path reads is ``CI``, and it disables the
    whole attempt rather than letting one through unserialised.
    """
    import ast
    import inspect

    for func in (upgrader.self_upgrade, upgrader._self_upgrade_pending, upgrader.run_self_upgrade):
        source = inspect.getsource(func)
        names = {
            node.args[0].value
            for node in ast.walk(ast.parse(source.lstrip()))
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "get"
            and getattr(node.func.value, "attr", None) == "environ"
            and node.args
            and isinstance(node.args[0], ast.Constant)
        }
        assert names <= {"CI"}, (
            f"{func.__name__} reads environment variables {sorted(names - {'CI'})}; "
            "no bypass variable may exist on this path (E030)"
        )

    stream = io.StringIO()
    with upgrade_held():
        with patch.dict("os.environ", {"ATDD_UPGRADE_NO_LOCK": "1"}), \
             patch.object(upgrader, "_resolve_latest_version", return_value="9.9.9"), \
             patch.object(upgrader, "_gate_version", return_value="4.0.0"), \
             patch.object(upgrader, "auto_upgrade") as never:
            assert upgrader.self_upgrade(stream=stream) == upgrader.SELF_UPGRADE_CONTENDED
    never.assert_not_called()
