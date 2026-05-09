# URN: test:judge-ambiguous-decisions:judge-and-issue-review:D001-SMOKE-001-judge-real-infrastructure
# Acceptance: acc:judge-ambiguous-decisions:D001-UNIT-003-every-call-writes-judgments-jsonl
# WMBT: wmbt:judge-ambiguous-decisions:D001
# Phase: SMOKE
# Layer: integration
"""SMOKE — `atdd judge` exercises the real CLI dispatcher, real coach
config loader, real frozen schema, and real filesystem JSONL writer.

Unit tests stub `find_repo_root` and call `run(...)` directly; this
file launches `python -m atdd judge ...` as a subprocess and asserts
that:

  1. The CLI dispatcher routes `judge` to `atdd.coach.commands.judge`.
  2. `coach.judge.fail_open` read from a real `.atdd/config.yaml`
     governs the LLM-unavailable path.
  3. The audit record written to disk validates against the
     repository's own `coach-judgment.schema.json`.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import jsonschema
import pytest
import yaml

pytestmark = [pytest.mark.platform]


REPO_ROOT = Path(__file__).resolve().parents[5]
SCHEMAS_DIR = REPO_ROOT / "src" / "atdd" / "coach" / "schemas"


def _judgment_schema() -> dict:
    return json.loads((SCHEMAS_DIR / "coach-judgment.schema.json").read_text())


def _conformant_schema_doc() -> dict:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "required": ["decision"],
        "additionalProperties": False,
        "properties": {"decision": {"type": "string", "enum": ["allow", "block"]}},
    }


def _write_workspace(workspace: Path, *, fail_open: bool | None = None) -> None:
    (workspace / ".atdd").mkdir()
    cfg: dict = {"version": "1.0"}
    if fail_open is not None:
        cfg["coach"] = {"judge": {"fail_open": fail_open}}
    (workspace / ".atdd" / "config.yaml").write_text(yaml.safe_dump(cfg))
    (workspace / "prompt.yaml").write_text(yaml.safe_dump({"prompt": "x"}))
    (workspace / "schema.json").write_text(json.dumps(_conformant_schema_doc()))


def _run_cli(workspace: Path, *args: str) -> subprocess.CompletedProcess:
    """Invoke the real `atdd judge` CLI in a fresh subprocess.

    Smoke discipline: we go through atdd.__main__ → atdd.cli → judge,
    not the in-process `run(...)` API. To register stub LLM clients in
    the child, we wrap the cli entry point in a tiny script that
    registers stubs against atdd.coach.commands.judge BEFORE handing off
    argv. This avoids sitecustomize timing problems with site-packages.
    """
    env = dict(os.environ)
    src = str(REPO_ROOT / "src")
    env["PYTHONPATH"] = f"{src}{os.pathsep}{env.get('PYTHONPATH', '')}"
    runner = textwrap.dedent("""
        import sys
        from atdd.coach.commands import judge as _j


        class _StubOK:
            def invoke(self, prompt):
                return {"decision": "allow"}


        class _StubDown:
            def invoke(self, prompt):
                raise _j.LLMUnavailable("network down")


        _j.register_llm_client("stub-ok", lambda: _StubOK())
        _j.register_llm_client("stub-down", lambda: _StubDown())

        from atdd.cli import main as _cli_main
        sys.argv = ["atdd", "judge"] + sys.argv[1:]
        sys.exit(_cli_main() or 0)
    """).lstrip()
    return subprocess.run(
        [sys.executable, "-c", runner, *args],
        cwd=str(workspace),
        capture_output=True,
        text=True,
        env=env,
    )


# ---------------------------------------------------------------------------
# Smoke 1: success path through the real dispatcher
# ---------------------------------------------------------------------------


def test_cli_dispatcher_routes_judge_and_writes_real_jsonl(tmp_path: Path):
    _write_workspace(tmp_path)
    result = _run_cli(
        tmp_path,
        "--prompt-template", "prompt.yaml",
        "--schema", "schema.json",
        "--inputs", "sha=abc123",
        "--call-site", "phase-advance",
        "--llm", "stub-ok",
    )
    assert result.returncode == 0, (
        f"stdout: {result.stdout!r}\nstderr: {result.stderr!r}"
    )
    printed = json.loads(result.stdout.strip().splitlines()[-1])
    assert printed == {"decision": "allow"}

    log = tmp_path / ".atdd" / "runtime" / "coach" / "judgments.jsonl"
    records = [json.loads(line) for line in log.read_text().splitlines() if line.strip()]
    assert len(records) == 1
    jsonschema.Draft202012Validator(_judgment_schema()).validate(records[0])
    assert records[0]["outcome"] == "ok"
    assert records[0]["call_site"] == "phase-advance"


# ---------------------------------------------------------------------------
# Smoke 2: real config loader honors coach.judge.fail_open=true
# ---------------------------------------------------------------------------


def test_real_config_loader_fail_open_true_exits_nonzero(tmp_path: Path):
    _write_workspace(tmp_path, fail_open=True)
    result = _run_cli(
        tmp_path,
        "--prompt-template", "prompt.yaml",
        "--schema", "schema.json",
        "--call-site", "phase-advance",
        "--llm", "stub-down",
    )
    assert result.returncode != 0
    log = tmp_path / ".atdd" / "runtime" / "coach" / "judgments.jsonl"
    records = [json.loads(line) for line in log.read_text().splitlines() if line.strip()]
    assert len(records) == 1
    jsonschema.Draft202012Validator(_judgment_schema()).validate(records[0])
    assert records[0]["outcome"] == "llm_unavailable"


# ---------------------------------------------------------------------------
# Smoke 3: real config loader default fail_open=false yields fallback
# ---------------------------------------------------------------------------


def test_real_config_loader_default_fail_open_false_returns_fallback(tmp_path: Path):
    _write_workspace(tmp_path)  # no override → default false
    result = _run_cli(
        tmp_path,
        "--prompt-template", "prompt.yaml",
        "--schema", "schema.json",
        "--call-site", "review-disposition",
        "--llm", "stub-down",
    )
    assert result.returncode == 0, (
        f"stdout: {result.stdout!r}\nstderr: {result.stderr!r}"
    )
    printed = json.loads(result.stdout.strip().splitlines()[-1])
    assert printed["decision"] == "block"
    assert printed["fail_open_used"] is True

    log = tmp_path / ".atdd" / "runtime" / "coach" / "judgments.jsonl"
    records = [json.loads(line) for line in log.read_text().splitlines() if line.strip()]
    assert len(records) == 1
    jsonschema.Draft202012Validator(_judgment_schema()).validate(records[0])
    assert records[0]["outcome"] == "fail_open_fallback"
    assert records[0]["call_site"] == "review-disposition"
