# URN: test:govern-lifecycle:operator-approval-token-gate:C012-UNIT-001-actor-is-observed-not-defaulted
# Acceptance: acc:govern-lifecycle:C012-UNIT-001-actor-is-observed-not-defaulted
# WMBT: wmbt:govern-lifecycle:C012
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""C012-UNIT-001 — the mint OBSERVES its actor instead of defaulting to ``$USER``.

``approve_command.py:71`` reads ``ns.by or os.environ.get("USER") or "operator"``.
An agent running inside the operator's shell IS ``$USER``, so every agent mint
files itself under the human — measured 2026-08-03 as 162 of 169 live tokens
naming a human account, with only three agent mints confirmed and each of those
only because the agent volunteered it.

The observation primitive already exists: ``atdd.state.agent_session.resolve_session``
(#1540) reads ambient process environment through a data-driven provider table,
never asks the agent, and returns ``None`` for a human at a plain shell. This
acceptance holds the mint to using it.

The environment is passed in explicitly rather than monkeypatched, so the test
asserts the same thing whether it runs under an agent or under a human — the
ambient session of whoever runs the suite is never an input.

RED state: ``run()`` takes no ``env`` keyword and reads ``os.environ`` directly,
so these calls fail before they can assert anything.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from atdd.coach.gate.approval import TOKEN_SCHEMA_VERSION, approval_relpath
from atdd.coach.gate.approve_command import run as run_approve
from atdd.state.agent_session import load_provider_table
from atdd.state.smoke_evidence import open_state_store

pytestmark = [pytest.mark.platform]

_ISSUE, _FROM, _TO = 1718, "INIT", "PLANNED"
_HUMAN = "alecfokapu"
_SESSION_ID = "1886c25f-4f38-466c-ae9a-7d94ff0d491f"
_UID = "c012-unit-001-actor-is-observed"
_BRANCH = "feat/mint-observes-its-actor"

# Read the provider row out of the shipped table rather than hardcoding a
# provider's env var name here: core learns no provider (#1540), and a test that
# names one would have to be edited every time a row is added.
_ROW = load_provider_table()[0]


@pytest.fixture(autouse=True)
def mintable_issue(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """BOTH preconditions the mint now requires: a branch (#1721) and a phase (#1735).

    Autouse because every test here mints, and neither precondition is a subject of
    this acceptance — which is about WHO the token says approved, not what it is
    bound to or which edge is live. One `upsert` carries both: `state` is where the
    issue is standing, `data["branch"]` is what the approval will be bound to.

    Seeding real state was chosen over a test-only bypass on the mint, and the
    argument is the same for both issues: a bypass would be a second ungated way to
    mint (#1619's defect one layer out) inside a file whose job is to prove the mint
    observes correctly, and a test that can route around the code it guards proves
    nothing (#1733).
    """
    monkeypatch.setenv("ATDD_CONTROL_ROOT", str(tmp_path))
    with open_state_store(control_root=tmp_path) as store:
        store.objects.upsert(_UID, "work_item", state=_FROM, data={"branch": _BRANCH})
        store.external_refs.link(_UID, "github", "issue", str(_ISSUE))


def _read_token(root: Path) -> dict:
    return json.loads((root / approval_relpath(_ISSUE, _FROM, _TO)).read_text())


def test_an_observed_session_is_recorded_and_the_operator_is_not_the_approver(tmp_path: Path):
    env = {"USER": _HUMAN, _ROW.session_env: _SESSION_ID}

    assert run_approve(
        [str(_ISSUE), "--transition", f"{_FROM}->{_TO}"], target_dir=tmp_path, env=env
    ) == 0
    token = _read_token(tmp_path)

    # The token names WHICH session produced it, so it traces to a transcript.
    assert token["agent_session"] == {
        "provider": _ROW.provider, "session_id": _SESSION_ID
    }
    # ...and the human whose shell the agent happened to run in is NOT recorded as
    # the approver. This is the whole defect: $USER is not an observation of who
    # approved, it is an observation of whose shell is open.
    assert _HUMAN not in token["approved_by"], (
        f"an agent mint recorded {token['approved_by']!r} as the approver while a "
        f"session was observable — the operator is still being credited"
    )
    # Every token the new path mints declares its regime.
    assert token["schema_version"] == TOKEN_SCHEMA_VERSION


def test_no_observed_session_records_the_human_account_and_no_agent_session(tmp_path: Path):
    # A human at a plain shell: no mapped session variable anywhere in the env.
    env = {"USER": _HUMAN}

    assert run_approve(
        [str(_ISSUE), "--transition", f"{_FROM}->{_TO}"], target_dir=tmp_path, env=env
    ) == 0
    token = _read_token(tmp_path)

    assert token["approved_by"] == _HUMAN
    # Absence of observation is recorded as absence, never as an invented identity
    # — the same discipline resolve_session itself keeps by returning None.
    assert "agent_session" not in token
    assert token["schema_version"] == TOKEN_SCHEMA_VERSION


def test_by_does_not_overwrite_an_observed_session(tmp_path: Path, capsys):
    env = {"USER": _HUMAN, _ROW.session_env: _SESSION_ID}

    assert run_approve(
        [str(_ISSUE), "--transition", f"{_FROM}->{_TO}", "--by", "the-operator-really"],
        target_dir=tmp_path, env=env,
    ) == 0
    token = _read_token(tmp_path)

    # --by may annotate; it may not assert what the process can see for itself.
    assert "the-operator-really" not in json.dumps(token)
    assert token["agent_session"]["session_id"] == _SESSION_ID
    # And the caller is told, rather than having the flag silently swallowed.
    assert "--by" in capsys.readouterr().out


def test_by_is_still_honoured_when_nothing_is_observed(tmp_path: Path):
    # With no session to contradict, --by remains the operator's way to record an
    # identity other than the shell account. The flag is demoted, not removed.
    env = {"USER": _HUMAN}

    assert run_approve(
        [str(_ISSUE), "--transition", f"{_FROM}->{_TO}", "--by", "operator-delegated"],
        target_dir=tmp_path, env=env,
    ) == 0
    assert _read_token(tmp_path)["approved_by"] == "operator-delegated"
