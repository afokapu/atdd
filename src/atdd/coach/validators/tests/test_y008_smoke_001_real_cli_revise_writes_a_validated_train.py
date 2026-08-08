# URN: test:govern-lifecycle:bind-issue-train:Y008-SMOKE-001-real-cli-revise-writes-a-validated-train
# Acceptance: acc:govern-lifecycle:Y008-SMOKE-001-real-cli-revise-writes-a-validated-train
# WMBT: wmbt:govern-lifecycle:Y008
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: Against the real shipped CLI as a subprocess, `atdd author issue --revise <N> --train <urn>` reaches the store and an unregistered value exits non-zero changing nothing.
"""SMOKE test for acc:govern-lifecycle:Y008-SMOKE-001-real-cli-revise-writes-a-validated-train.

wagon: govern-lifecycle | feature: bind-issue-train | WMBT: wmbt:govern-lifecycle:Y008

An in-process unit proves the seam threads the argument; it does not prove the
shipped entry point does. That distinction is the whole of #1635's Break 4 — the
flag looked functional because the command exited 0 and the body changed — and it
is doubly load-bearing here, because until #1590 this exact invocation printed
``--revise cannot honour --train`` and exited 2. A test that only drove the
internal chain could not tell the two regimes apart.

Real: a real ``python -m atdd`` subprocess, a real on-disk SQLite State Store, and
a real ``plan/`` tree belonging to a repository that is NOT atdd. The GitHub
projection is made unreachable by pointing PATH at a directory with no ``gh``, so
the outbox path is taken and the store write must stand on its own.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from ._bind_issue_train_helpers import (
    ABSENT_TRAIN,
    CONSUMER_FEATURE,
    CONSUMER_TRAIN,
    CONSUMER_TRAIN_LEGACY,
    control_root,
    open_store,
    read_issue_data,
    seed_issue,
    write_consumer_plan_tree,
)

pytestmark = [pytest.mark.platform]

_ISSUE = 93590
_REPO_SRC = Path(__file__).resolve().parents[4]  # .../src


def _run_cli(root: Path, *args: str) -> subprocess.CompletedProcess:
    """Invoke the real CLI in a separate process against ``root``."""
    env = dict(os.environ)
    env["PYTHONPATH"] = str(_REPO_SRC)
    env["ATDD_CONTROL_ROOT"] = str(root)
    # No `gh` on PATH: the GitHub projection must be unreachable so the store
    # write is what the assertion observes.
    (root / "empty-bin").mkdir(exist_ok=True)
    env["PATH"] = str(root / "empty-bin")
    return subprocess.run(
        [sys.executable, "-m", "atdd", "author", "issue", "--revise", *args],
        cwd=root, env=env, capture_output=True, text=True, timeout=180,
    )


@pytest.fixture()
def repo(tmp_path):
    root = control_root(tmp_path)
    write_consumer_plan_tree(root)
    store = open_store(root)
    seed_issue(store, slug="smoke-train-probe", issue_number=_ISSUE, train=None)
    store.conn.commit()

    # A schema-valid body: `_run_issue_revise` gates on the body schema before it
    # reaches the train check, so a hand-rolled fragment would make the CLI exit
    # non-zero for a schema reason and the assertions would prove nothing.
    from atdd.planner.commands.author import create_issue_body

    body = tmp_path / "body.md"
    body.write_text(
        create_issue_body({"title": "smoke train probe", "feature": CONSUMER_FEATURE}),
        encoding="utf-8",
    )
    return root, open_store(root), body


def _read_train(store):
    return read_issue_data(store, _ISSUE).get("train")


def test_real_cli_revise_writes_the_train_to_the_store(repo) -> None:
    """The shipped artifact writes the field. Until #1590 it refused the flag."""
    root, store, _body = repo

    result = _run_cli(root, str(_ISSUE), "--train", CONSUMER_TRAIN)

    assert result.returncode == 0, (
        f"real CLI revise exited {result.returncode}\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert _read_train(open_store(root)) == CONSUMER_TRAIN, (
        "the real CLI exited 0 and left the stored train unchanged — the shape "
        "the flag had before #1590, when it was refused outright"
    )


def test_the_real_cli_no_longer_refuses_the_flag(repo) -> None:
    """The discriminator between the two regimes.

    #1661's refusal also exited non-zero and also named ``--train``, so an exit
    code alone cannot distinguish "refused by design" from "rejected the value".
    The refusal text can.
    """
    root, _store, _body = repo

    result = _run_cli(root, str(_ISSUE), "--train", CONSUMER_TRAIN)
    combined = (result.stdout or "") + (result.stderr or "")

    assert "cannot honour --train" not in combined, (
        f"the shipped CLI still refuses --train by name:\n{combined}"
    )
    assert CONSUMER_TRAIN in combined, (
        "the CLI wrote a train without naming it, so an operator cannot tell a "
        f"successful write from a silently-ignored flag:\n{combined}"
    )


def test_a_resolvable_alias_reaches_the_store_through_the_real_cli(repo) -> None:
    """Legacy spellings are 27 of the live corpus. The shipped path must take them."""
    root, _store, _body = repo

    result = _run_cli(root, str(_ISSUE), "--train", CONSUMER_TRAIN_LEGACY)

    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
    assert _read_train(open_store(root)) == CONSUMER_TRAIN_LEGACY


def test_the_store_write_stands_when_the_projection_is_deferred(repo) -> None:
    """Provider unreachable must not cost the reference."""
    root, _store, body = repo

    result = _run_cli(root, str(_ISSUE), "--train", CONSUMER_TRAIN,
                      "--body-file", str(body))

    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
    assert _read_train(open_store(root)) == CONSUMER_TRAIN, (
        "the reference was lost because the GitHub projection was unreachable; "
        "the store is authoritative and must not depend on provider reachability"
    )


def test_an_unregistered_train_exits_non_zero_and_changes_nothing(repo) -> None:
    """The refusal is emitted by the SHIPPED entry point, not only by the seam."""
    root, _store, body = repo

    _run_cli(root, str(_ISSUE), "--train", CONSUMER_TRAIN)   # a reference to protect
    before = _read_train(open_store(root))
    assert before == CONSUMER_TRAIN, "the fixture's precondition did not hold"

    result = _run_cli(root, str(_ISSUE), "--body-file", str(body),
                      "--train", ABSENT_TRAIN)

    assert result.returncode != 0, (
        "the real CLI accepted a train that resolves to no registered train"
    )
    combined = (result.stdout or "") + (result.stderr or "")
    assert ABSENT_TRAIN in combined, (
        "the CLI exited non-zero without naming the value that failed to resolve, "
        f"so the refusal is not attributable to registry resolution:\n{combined}"
    )
    assert _read_train(open_store(root)) == before, (
        "a refused revision still mutated the stored train"
    )
