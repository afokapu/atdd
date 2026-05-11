# URN: test:integration-hardening:coach-single-command-driver:C001-INTEGRATION-003-judge-also-works
# Acceptance: acc:integration-hardening:C001-INTEGRATION-003-judge-also-works
# WMBT: wmbt:integration-hardening:C001
# Phase: GREEN
# Layer: application
"""C001-INTEGRATION-003 — After importing llm_clients with a stub subprocess shim,
atdd judge run() completes successfully and writes a judgments.jsonl line.

Spec: issue #592 acc:integration-hardening:C001-INTEGRATION-003-judge-also-works
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
import yaml


_VALID_RESPONSE = {"decision": "block", "reason": "stub response", "confidence": 0.9}

_SCHEMA = {
    "type": "object",
    "required": ["decision", "reason", "confidence"],
    "properties": {
        "decision": {"type": "string"},
        "reason": {"type": "string"},
        "confidence": {"type": "number"},
    },
    "additionalProperties": False,
}


@pytest.fixture
def judge_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".atdd").mkdir()
    (tmp_path / ".atdd" / "config.yaml").write_text(yaml.safe_dump({"version": "1.0"}))

    schema_path = tmp_path / "schema.json"
    schema_path.write_text(json.dumps(_SCHEMA))

    prompt_path = tmp_path / "prompt.yaml"
    prompt_path.write_text(yaml.safe_dump({"prompt": "Should we block? {context}"}))

    return tmp_path


@pytest.fixture(autouse=True)
def _reset_registry():
    from atdd.coach.commands import judge as judge_mod

    snapshot = dict(judge_mod.LLM_REGISTRY)
    judge_mod.LLM_REGISTRY.clear()
    yield
    judge_mod.LLM_REGISTRY.clear()
    judge_mod.LLM_REGISTRY.update(snapshot)


def _make_stub_subprocess_run(response_json: dict):
    """Return a mock subprocess.run that yields JSON output."""
    def fake_run(cmd, *, input=None, capture_output=False, text=False, timeout=None, **kw):
        result = MagicMock()
        result.returncode = 0
        result.stdout = json.dumps(response_json)
        result.stderr = ""
        return result
    return fake_run


def test_judge_run_succeeds_with_subprocess_shim(judge_workspace: Path):
    """judge.run() returns 0 when a subprocess-shim client is registered."""
    from atdd.coach.commands import judge as judge_mod
    from atdd.coach.commands.llm_clients._subprocess_shim import ClaudeSubprocessClient

    fake_claude = str(judge_workspace / "claude")
    client = ClaudeSubprocessClient(
        claude_bin=fake_claude,
        model_id="claude-haiku-4-5-20251001",
    )

    stub_run = _make_stub_subprocess_run(_VALID_RESPONSE)
    with patch("subprocess.run", side_effect=stub_run):
        judge_mod.register_llm_client("claude-haiku", lambda c=client: c)

        ret = judge_mod.run(
            prompt_template=str(judge_workspace / "prompt.yaml"),
            schema=str(judge_workspace / "schema.json"),
            inputs=["context=test"],
            call_site="phase-advance",
            llm="claude-haiku",
        )

    assert ret == 0, f"judge.run() returned {ret}, expected 0"


def test_judge_run_writes_judgments_jsonl(judge_workspace: Path):
    """judge.run() appends a success line to judgments.jsonl."""
    from atdd.coach.commands import judge as judge_mod
    from atdd.coach.commands.llm_clients._subprocess_shim import ClaudeSubprocessClient

    fake_claude = str(judge_workspace / "claude")
    client = ClaudeSubprocessClient(
        claude_bin=fake_claude,
        model_id="claude-haiku-4-5-20251001",
    )

    stub_run = _make_stub_subprocess_run(_VALID_RESPONSE)
    with patch("subprocess.run", side_effect=stub_run):
        judge_mod.register_llm_client("claude-haiku", lambda c=client: c)

        judge_mod.run(
            prompt_template=str(judge_workspace / "prompt.yaml"),
            schema=str(judge_workspace / "schema.json"),
            inputs=["context=test"],
            call_site="phase-advance",
            llm="claude-haiku",
        )

    judgments_path = judge_workspace / ".atdd" / "runtime" / "coach" / "judgments.jsonl"
    assert judgments_path.exists(), "judgments.jsonl was not created"
    lines = [json.loads(line) for line in judgments_path.read_text().splitlines() if line.strip()]
    assert len(lines) >= 1, "No judgment lines written"
    assert lines[-1]["outcome"] == "ok", f"Expected outcome=ok, got {lines[-1]['outcome']}"


def test_subprocess_client_extracts_json_from_markdown_wrapper(judge_workspace: Path):
    """ClaudeSubprocessClient.invoke() strips ```json ... ``` markdown wrapper."""
    from atdd.coach.commands.llm_clients._subprocess_shim import ClaudeSubprocessClient

    fake_claude = str(judge_workspace / "claude")
    client = ClaudeSubprocessClient(claude_bin=fake_claude, model_id="claude-haiku-4-5-20251001")

    markdown_output = '```json\n{"key": "value"}\n```'
    stub_run = MagicMock()
    stub_run.return_value = MagicMock(returncode=0, stdout=markdown_output, stderr="")

    with patch("subprocess.run", stub_run):
        result = client.invoke("test prompt")

    assert result == {"key": "value"}
