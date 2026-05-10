# URN: test:drive-state-machine:coach-state-machine-and-runtime:D002-UNIT-001-subcommands-resolve
# Acceptance: acc:drive-state-machine:D002-UNIT-001-subcommands-resolve
# WMBT: wmbt:drive-state-machine:D002
# Phase: RED
# Layer: application
"""D002-UNIT-001 — `atdd agent <subcommand>` resolves and writes the
expected files under `.atdd/runtime/agents/<id>/` per spec §3.2.

Subcommands covered: heartbeat, event, ask, escalate, done, context, review.
Commit is exercised in D002-UNIT-002 so the git-side concerns stay out of
this file.
"""
from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

import atdd

pytestmark = [pytest.mark.platform]

ATDD_PKG_DIR = Path(atdd.__file__).resolve().parent
RUNTIME_EVENT_SCHEMA = (
    ATDD_PKG_DIR / "coach" / "schemas" / "runtime-event.schema.json"
)


@pytest.fixture
def runtime_root(tmp_path: Path) -> Path:
    return tmp_path / ".atdd" / "runtime"


@pytest.fixture
def agent_id() -> str:
    return "agent-J2-test"


# ---------------------------------------------------------------------------
# Module surface
# ---------------------------------------------------------------------------


def test_module_exposes_all_subcommand_callables():
    """The eight subcommand functions named in spec §5.3 must exist as
    callables on `atdd.coach.commands.agent`."""
    from atdd.coach.commands import agent

    for name in (
        "cmd_heartbeat",
        "cmd_event",
        "cmd_commit",
        "cmd_ask",
        "cmd_escalate",
        "cmd_done",
        "cmd_context",
        "cmd_review",
    ):
        assert callable(getattr(agent, name)), (
            f"missing callable atdd.coach.commands.agent.{name}"
        )


def test_module_exposes_argparse_dispatcher():
    from atdd.coach.commands import agent

    assert callable(getattr(agent, "main", None))
    assert callable(getattr(agent, "run", None))


# ---------------------------------------------------------------------------
# heartbeat — single-doc JSON, rewritten in place
# ---------------------------------------------------------------------------


def test_heartbeat_writes_single_doc_json(runtime_root: Path, agent_id: str):
    from atdd.coach.commands import agent

    path = agent.cmd_heartbeat(
        agent_id=agent_id,
        current_step="writing tests",
        runtime_root=runtime_root,
    )
    assert path == runtime_root / "agents" / agent_id / "heartbeat.json"
    assert path.is_file()

    payload = json.loads(path.read_text())
    assert "timestamp" in payload
    assert payload["current_step"] == "writing tests"
    # ISO-8601 UTC: must end with Z (or include +00:00) — single-doc JSON.
    assert payload["timestamp"].endswith("Z")


def test_heartbeat_rewritten_not_appended(runtime_root: Path, agent_id: str):
    from atdd.coach.commands import agent

    p1 = agent.cmd_heartbeat(agent_id=agent_id, runtime_root=runtime_root)
    first_payload = json.loads(p1.read_text())

    p2 = agent.cmd_heartbeat(
        agent_id=agent_id,
        current_step="second tick",
        runtime_root=runtime_root,
    )
    assert p1 == p2
    # The file is a single JSON document (not JSON-lines).
    text = p2.read_text()
    assert text.lstrip().startswith("{")
    parsed = json.loads(text)
    assert parsed["current_step"] == "second tick"
    assert parsed["timestamp"] >= first_payload["timestamp"]


# ---------------------------------------------------------------------------
# event — append-only JSON-lines conforming to runtime-event.schema.json
# ---------------------------------------------------------------------------


def test_event_appends_to_jsonl_conforming_to_schema(
    runtime_root: Path, agent_id: str,
):
    from atdd.coach.commands import agent

    schema = json.loads(RUNTIME_EVENT_SCHEMA.read_text())

    record = agent.cmd_event(
        "heartbeat",
        agent_id=agent_id,
        data={"note": "first"},
        runtime_root=runtime_root,
    )
    path = runtime_root / "agents" / agent_id / "events.jsonl"
    assert path.is_file()

    lines = [ln for ln in path.read_text().splitlines() if ln.strip()]
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    jsonschema.validate(parsed, schema)
    assert parsed["event_type"] == "heartbeat"
    assert parsed["agent_id"] == agent_id
    assert parsed == record

    agent.cmd_event(
        "commit_observed",
        agent_id=agent_id,
        data={"sha": "deadbeef"},
        runtime_root=runtime_root,
    )
    lines2 = [ln for ln in path.read_text().splitlines() if ln.strip()]
    assert len(lines2) == 2  # append-only
    second = json.loads(lines2[1])
    jsonschema.validate(second, schema)
    assert second["event_type"] == "commit_observed"


def test_event_rejects_unknown_event_type(runtime_root: Path, agent_id: str):
    from atdd.coach.commands import agent

    with pytest.raises(ValueError):
        agent.cmd_event(
            "not_a_real_type", agent_id=agent_id, runtime_root=runtime_root,
        )


# ---------------------------------------------------------------------------
# ask — append-only JSON-lines under questions.jsonl
# ---------------------------------------------------------------------------


def test_ask_appends_structured_record(runtime_root: Path, agent_id: str):
    from atdd.coach.commands import agent

    record = agent.cmd_ask(
        question="proceed with refactor?",
        type="approval",
        agent_id=agent_id,
        runtime_root=runtime_root,
    )
    path = runtime_root / "agents" / agent_id / "questions.jsonl"
    lines = [ln for ln in path.read_text().splitlines() if ln.strip()]
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed["question"] == "proceed with refactor?"
    assert parsed["type"] == "approval"
    assert parsed["question_id"]
    assert parsed["timestamp"].endswith("Z")
    assert parsed == record


def test_ask_rejects_unknown_type(runtime_root: Path, agent_id: str):
    from atdd.coach.commands import agent

    with pytest.raises(ValueError):
        agent.cmd_ask(
            question="?", type="ambiguous",
            agent_id=agent_id, runtime_root=runtime_root,
        )


# ---------------------------------------------------------------------------
# escalate — append-only JSON-lines under escalations.jsonl
# ---------------------------------------------------------------------------


def test_escalate_appends_with_severity(runtime_root: Path, agent_id: str):
    from atdd.coach.commands import agent

    record = agent.cmd_escalate(
        reason="blocked by missing schema",
        severity="block",
        agent_id=agent_id,
        runtime_root=runtime_root,
    )
    path = runtime_root / "agents" / agent_id / "escalations.jsonl"
    lines = [ln for ln in path.read_text().splitlines() if ln.strip()]
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed["reason"] == "blocked by missing schema"
    assert parsed["severity"] == "block"
    assert parsed["timestamp"].endswith("Z")
    assert parsed == record


def test_escalate_rejects_unknown_severity(runtime_root: Path, agent_id: str):
    from atdd.coach.commands import agent

    with pytest.raises(ValueError):
        agent.cmd_escalate(
            reason="x", severity="critical",
            agent_id=agent_id, runtime_root=runtime_root,
        )


# ---------------------------------------------------------------------------
# done — single final-summary record
# ---------------------------------------------------------------------------


def test_done_writes_final_summary(runtime_root: Path, agent_id: str):
    from atdd.coach.commands import agent

    path = agent.cmd_done(
        agent_id=agent_id,
        summary="J2 complete",
        runtime_root=runtime_root,
    )
    assert path == runtime_root / "agents" / agent_id / "done.json"
    payload = json.loads(path.read_text())
    assert payload["summary"] == "J2 complete"
    assert payload["timestamp"].endswith("Z")


# ---------------------------------------------------------------------------
# context — prints phase + WMBT context from spawn-time bundle
# ---------------------------------------------------------------------------


def test_context_reads_spawn_bundle_and_returns_dict(
    runtime_root: Path, agent_id: str,
):
    from atdd.coach.commands import agent

    bundle_path = runtime_root / "agents" / agent_id / "context.json"
    bundle_path.parent.mkdir(parents=True, exist_ok=True)
    bundle_path.write_text(json.dumps({
        "phase": "RED",
        "wmbt_urn": "wmbt:drive-state-machine:D002",
        "issue": 497,
    }))

    ctx = agent.cmd_context(agent_id=agent_id, runtime_root=runtime_root)
    assert ctx["phase"] == "RED"
    assert ctx["wmbt_urn"] == "wmbt:drive-state-machine:D002"
    assert ctx["issue"] == 497


# ---------------------------------------------------------------------------
# review — write under reviews/<review-id>.json
# ---------------------------------------------------------------------------


def test_review_writes_under_reviews_subdir(
    runtime_root: Path, agent_id: str, tmp_path: Path,
):
    from atdd.coach.commands import agent

    # Write a reviewer manifest so the persona check passes
    agent_dir = runtime_root / "agents" / agent_id
    agent_dir.mkdir(parents=True, exist_ok=True)
    manifest = agent_dir / "manifest.json"
    manifest.write_text(json.dumps({"persona": "reviewer", "agent_id": agent_id}))

    report_data = {
        "review_id": "rev-d002-test",
        "target_commit": "0123abcd",
        "reviewer_agent_id": agent_id,
        "wmbt_urn": "wmbt:drive-state-machine:D002",
        "phase": "GREEN",
        "verdict": "pass",
        "tier1_risk_score": 0,
        "findings": [],
        "ac_coverage": {"acc:drive-state-machine:D002-UNIT-001": "covered"},
        "summary": "All clean.",
    }
    report = tmp_path / "report.json"
    report.write_text(json.dumps(report_data))

    path = agent.cmd_review(
        target_commit="0123abcd",
        report_file=str(report),
        agent_id=agent_id,
        runtime_root=runtime_root,
    )
    assert path.parent == runtime_root / "agents" / agent_id / "reviews"
    assert path.name == "rev-d002-test.json"

    payload = json.loads(path.read_text())
    assert payload["review_id"] == "rev-d002-test"
    assert payload["verdict"] == "pass"


def test_review_rejects_missing_report_file(
    runtime_root: Path, agent_id: str, tmp_path: Path,
):
    from atdd.coach.commands import agent

    with pytest.raises(FileNotFoundError):
        agent.cmd_review(
            target_commit="abc",
            report_file=str(tmp_path / "missing.md"),
            agent_id=agent_id,
            runtime_root=runtime_root,
        )


# ---------------------------------------------------------------------------
# CLI dispatcher — every subcommand parses (no internal sub-help required)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "subcommand",
    ["heartbeat", "event", "commit", "ask", "escalate", "done", "context", "review"],
)
def test_cli_dispatcher_recognizes_every_subcommand(subcommand: str):
    """`atdd agent <subcommand> --help` exits 0 — proves the subparser
    is wired in, independent of any flags it might require."""
    from atdd.coach.commands import agent

    with pytest.raises(SystemExit) as exc:
        agent.main([subcommand, "--help"])
    assert exc.value.code == 0
