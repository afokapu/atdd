# URN: test:govern-lifecycle:honest-outbox-deferral:C015-SMOKE-001-real-cli-refuses-to-report-a-stalled-queue-as-drained
# Acceptance: acc:govern-lifecycle:C015-SMOKE-001-real-cli-refuses-to-report-a-stalled-queue-as-drained
# WMBT: wmbt:govern-lifecycle:C015
# Phase: SMOKE
# Runtime: python
# Layer: integration
# Assertion: behavioral
# Purpose: The exact invocation an operator runs to check whether sync is healthy stops answering 0 over a queue it could not move.
"""C015-SMOKE-001 — the real CLI refuses to report a stalled queue as drained.

The unit siblings assert the verdict; this asserts that it reaches a shell. The
invocation is a real subprocess of the shipped entry point against a real
migrated State Store under an isolated Control Root, with real pending rows
written through the store's own writer and the provider registry left exactly as
this repository ships it — empty. Nothing about the store, the engine or the
registry is monkeypatched.

That combination is the live state measured on 2026-08-03: 30 rows pending, the
oldest enqueued 2026-07-09, exactly 2 rows ever sent, ``discover_providers()``
empty — and `atdd state sync --push` reporting ``0 pushed, 0 failed`` and exiting
0 throughout.

The registered-provider leg is the discriminator. Without it a non-zero exit
cannot be distinguished from `--push` simply refusing to work, which would be a
different defect wearing this fix's clothes.

RED state: the command exits 0 over the stalled store.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

import atdd
from atdd.state.db import connect, init_state_store
from atdd.state.providers import clear_providers, register_provider
from atdd.state.store import StateStore

pytestmark = pytest.mark.smoke


class _AcceptingProvider:
    """A registered provider that accepts every operation. Real registration
    through the public seam — the discriminator leg, not a patch."""

    name = "github"

    def __init__(self) -> None:
        self.calls: list = []

    def push(self, operation, payload) -> None:
        self.calls.append((operation, payload))
        return None


@pytest.fixture()
def stalled_store(tmp_path: Path) -> Path:
    """A real Control Root whose real State Store carries real pending rows."""
    root = tmp_path / "project"
    (root / ".atdd").mkdir(parents=True)
    (root / ".atdd" / "config.yaml").write_text("themes: []\n", encoding="utf-8")

    conn = connect(init_state_store(start=root))
    try:
        store = StateStore(conn)
        store.sync.enqueue_outbox("github", "create_issue", {"slug": "orphan-a"})
        store.sync.enqueue_outbox("github", "update_issue", {"issue_number": 1711})
    finally:
        conn.close()
    return root


def _run_cli(root: Path, *args: str) -> subprocess.CompletedProcess:
    """The shipped entry point in a real child process — not an in-process call."""
    env = dict(os.environ)
    # Wherever the package lives (src/ in a checkout, site-packages installed),
    # the child imports the same one this test imported.
    env["PYTHONPATH"] = str(Path(atdd.__file__).resolve().parent.parent)
    env["ATDD_CONTROL_ROOT"] = str(root)
    return subprocess.run(
        [sys.executable, "-m", "atdd", "state", "sync", *args],
        cwd=str(root), env=env, capture_output=True, text=True,
    )


def _pending(root: Path) -> int:
    conn = connect(init_state_store(start=root))
    try:
        return len(StateStore(conn).sync.pending_outbox())
    finally:
        conn.close()


def test_real_push_over_a_stalled_queue_exits_non_zero(stalled_store):
    """The headline. An operator checking sync health gets an answer they can act on."""
    proc = _run_cli(stalled_store, "--push")

    assert proc.returncode != 0, (
        "a queue nothing could move must not answer with the exit code of a drain; "
        f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
    )


def test_the_output_names_the_verdict_and_the_unregistered_provider(stalled_store):
    """Actionable without opening the table: which verdict, and whose registration
    is missing."""
    proc = _run_cli(stalled_store, "--push")
    output = proc.stdout + proc.stderr

    assert "could_not_check" in output.lower()
    assert "github" in output


def test_the_refusal_destroys_nothing(stalled_store):
    """The queue is not safely drainable — 7 of the live update_issue payloads are
    older than the published body and 4 of the create rows are byte-identical
    duplicates. A refusal that silently sent anything would be worse than the
    defect it replaces."""
    _run_cli(stalled_store, "--push")

    assert _pending(stalled_store) == 2


def test_the_backlog_is_reported_with_its_age(stalled_store):
    """Report mode surfaces accumulation rather than holding it."""
    proc = _run_cli(stalled_store)

    assert "2 pending" in proc.stdout
    assert "oldest" in proc.stdout.lower()


def test_with_a_provider_registered_the_same_store_drains_and_exits_zero(stalled_store):
    """The discriminator: the non-zero exit above is the stalled state, not the flag.

    Registration is in-process, so this leg drives ``run_sync_cli`` directly — the
    same function the subprocess above reaches, through the public registry seam
    rather than a patch.
    """
    from atdd.state.sync_cli import run_sync_cli

    provider = _AcceptingProvider()
    clear_providers()
    register_provider("github", lambda: provider)
    try:
        code = run_sync_cli(["--root", str(stalled_store), "--push"])
    finally:
        clear_providers()

    assert code == 0
    assert len(provider.calls) == 2
    assert _pending(stalled_store) == 0
