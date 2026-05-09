# URN: test:judge-ambiguous-decisions:judge-and-issue-review:D001-UNIT-001-judge-cli-returns-structured-or-fails-loud
# Acceptance: acc:judge-ambiguous-decisions:D001-UNIT-001-judge-cli-returns-structured-or-fails-loud
# WMBT: wmbt:judge-ambiguous-decisions:D001
# Phase: RED
# Layer: application
"""D001-UNIT-001 — `atdd judge` returns a schema-conformant structured
response or fails loudly with a non-zero exit and a clear validation
error.

Spec §5.5 / §6.9: the CLI signature is

    atdd judge --prompt-template <yaml> --schema <json>
               --inputs key=val key2=@file
               --call-site <one-of-six>
               [--llm <id>]

The command renders the prompt template against the inputs (with
`@file` resolution), invokes the configured LLM via the registry, and
validates the response against the supplied JSON Schema before
printing it. A schema-violating payload exits non-zero and names the
offending field; an unknown `--llm <id>` raises a clear error.

This test file owns the "structured-or-loud" half of the contract;
fail-open behavior lives in D001-UNIT-002 and audit-trail discipline
in D001-UNIT-003.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

pytestmark = [pytest.mark.platform]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _write_prompt_template(path: Path, body: str) -> None:
    path.write_text(yaml.safe_dump({"prompt": body}))


def _write_schema(path: Path, schema: dict) -> None:
    path.write_text(json.dumps(schema))


def _conformant_schema() -> dict:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "required": ["decision", "rationale"],
        "additionalProperties": False,
        "properties": {
            "decision": {"type": "string", "enum": ["allow", "block", "escalate"]},
            "rationale": {"type": "string", "minLength": 1},
        },
    }


@pytest.fixture
def judge_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Isolated repo-root with .atdd/ scaffold and runtime dir."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".atdd").mkdir()
    (tmp_path / ".atdd" / "config.yaml").write_text(yaml.safe_dump({"version": "1.0"}))
    return tmp_path


# ---------------------------------------------------------------------------
# Stub LLM helpers
# ---------------------------------------------------------------------------


def _register_stub(name: str, payload):
    """Install a stub LLM client that returns `payload` for every prompt."""
    from atdd.coach.commands import judge as judge_mod

    def _factory():
        return _StubClient(payload)

    judge_mod.register_llm_client(name, _factory)


class _StubClient:
    def __init__(self, payload):
        self._payload = payload

    def invoke(self, prompt: str):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


@pytest.fixture(autouse=True)
def _reset_registry():
    """Each test starts with a clean LLM registry so stubs do not leak."""
    from atdd.coach.commands import judge as judge_mod

    snapshot = dict(judge_mod.LLM_REGISTRY)
    judge_mod.LLM_REGISTRY.clear()
    yield
    judge_mod.LLM_REGISTRY.clear()
    judge_mod.LLM_REGISTRY.update(snapshot)


# ---------------------------------------------------------------------------
# AC-UNIT-001: structured response on success
# ---------------------------------------------------------------------------


class TestStructuredResponseOnConformantPayload:
    """A schema-conformant payload exits 0 and prints the response."""

    def test_returns_zero_and_prints_structured_response(
        self, judge_workspace: Path, capsys: pytest.CaptureFixture
    ):
        from atdd.coach.commands.judge import run

        prompt = judge_workspace / "prompt.yaml"
        schema = judge_workspace / "schema.json"
        _write_prompt_template(prompt, "should we suppress {sha}?")
        _write_schema(schema, _conformant_schema())

        payload = {"decision": "allow", "rationale": "no risk"}
        _register_stub("stub-ok", payload)

        rc = run(
            prompt_template=str(prompt),
            schema=str(schema),
            inputs=["sha=abc123"],
            llm="stub-ok",
            call_site="phase-advance",
        )
        assert rc == 0
        out = capsys.readouterr().out
        printed = json.loads(out.strip().splitlines()[-1])
        assert printed == payload

    def test_response_validates_against_schema(self, judge_workspace: Path):
        from atdd.coach.commands.judge import run

        prompt = judge_workspace / "p.yaml"
        schema = judge_workspace / "s.json"
        _write_prompt_template(prompt, "x")
        _write_schema(schema, _conformant_schema())
        _register_stub("ok", {"decision": "block", "rationale": "risky"})

        # Conformant payload → zero exit (validation passed).
        assert run(
            prompt_template=str(prompt),
            schema=str(schema),
            inputs=[],
            llm="ok",
            call_site="phase-advance",
        ) == 0


# ---------------------------------------------------------------------------
# AC-UNIT-001: schema violations exit non-zero with field-pointing message
# ---------------------------------------------------------------------------


class TestSchemaViolationFailsLoudly:
    def test_missing_required_field_exits_nonzero(
        self, judge_workspace: Path, capsys: pytest.CaptureFixture
    ):
        from atdd.coach.commands.judge import run

        prompt = judge_workspace / "p.yaml"
        schema = judge_workspace / "s.json"
        _write_prompt_template(prompt, "x")
        _write_schema(schema, _conformant_schema())
        _register_stub("violator", {"decision": "allow"})  # missing rationale

        rc = run(
            prompt_template=str(prompt),
            schema=str(schema),
            inputs=[],
            llm="violator",
            call_site="phase-advance",
        )
        assert rc != 0
        captured = capsys.readouterr()
        msg = (captured.err + captured.out).lower()
        assert "rationale" in msg
        assert "schema" in msg or "valid" in msg

    def test_wrong_enum_value_names_offending_field(
        self, judge_workspace: Path, capsys: pytest.CaptureFixture
    ):
        from atdd.coach.commands.judge import run

        prompt = judge_workspace / "p.yaml"
        schema = judge_workspace / "s.json"
        _write_prompt_template(prompt, "x")
        _write_schema(schema, _conformant_schema())
        _register_stub(
            "bogus-enum", {"decision": "maybe", "rationale": "..."}
        )

        rc = run(
            prompt_template=str(prompt),
            schema=str(schema),
            inputs=[],
            llm="bogus-enum",
            call_site="phase-advance",
        )
        assert rc != 0
        captured = capsys.readouterr()
        msg = (captured.err + captured.out).lower()
        assert "decision" in msg

    def test_wrong_type_names_offending_field(
        self, judge_workspace: Path, capsys: pytest.CaptureFixture
    ):
        from atdd.coach.commands.judge import run

        prompt = judge_workspace / "p.yaml"
        schema = judge_workspace / "s.json"
        _write_prompt_template(prompt, "x")
        _write_schema(schema, _conformant_schema())
        _register_stub(
            "wrong-type", {"decision": 42, "rationale": "..."}
        )

        rc = run(
            prompt_template=str(prompt),
            schema=str(schema),
            inputs=[],
            llm="wrong-type",
            call_site="phase-advance",
        )
        assert rc != 0
        captured = capsys.readouterr()
        msg = (captured.err + captured.out).lower()
        assert "decision" in msg


# ---------------------------------------------------------------------------
# AC-UNIT-001: @file inputs resolve before rendering
# ---------------------------------------------------------------------------


class TestInputResolution:
    def test_at_file_input_resolves_to_file_contents(
        self, judge_workspace: Path
    ):
        from atdd.coach.commands import judge as judge_mod
        from atdd.coach.commands.judge import run

        prompt = judge_workspace / "p.yaml"
        schema = judge_workspace / "s.json"
        ctx_file = judge_workspace / "ctx.txt"
        ctx_file.write_text("THE-FILE-CONTENTS")
        _write_prompt_template(prompt, "context: {ctx}")
        _write_schema(schema, _conformant_schema())

        captured_prompts: list[str] = []

        def _capture_factory():
            class _Cap:
                def invoke(self, p: str):
                    captured_prompts.append(p)
                    return {"decision": "allow", "rationale": "ok"}
            return _Cap()

        judge_mod.register_llm_client("capture", _capture_factory)

        rc = run(
            prompt_template=str(prompt),
            schema=str(schema),
            inputs=[f"ctx=@{ctx_file}"],
            llm="capture",
            call_site="phase-advance",
        )
        assert rc == 0
        assert captured_prompts, "LLM was never invoked"
        assert "THE-FILE-CONTENTS" in captured_prompts[0]
        assert "@" not in captured_prompts[0]  # placeholder resolved

    def test_plain_kv_input_substitutes_into_template(
        self, judge_workspace: Path
    ):
        from atdd.coach.commands import judge as judge_mod
        from atdd.coach.commands.judge import run

        prompt = judge_workspace / "p.yaml"
        schema = judge_workspace / "s.json"
        _write_prompt_template(prompt, "sha={sha}")
        _write_schema(schema, _conformant_schema())

        captured: list[str] = []

        def _factory():
            class _Cap:
                def invoke(self, p: str):
                    captured.append(p)
                    return {"decision": "allow", "rationale": "ok"}
            return _Cap()

        judge_mod.register_llm_client("cap", _factory)

        rc = run(
            prompt_template=str(prompt),
            schema=str(schema),
            inputs=["sha=abc123"],
            llm="cap",
            call_site="phase-advance",
        )
        assert rc == 0
        assert captured == ["sha=abc123"]

    def test_at_file_with_missing_path_exits_nonzero(
        self, judge_workspace: Path, capsys: pytest.CaptureFixture
    ):
        from atdd.coach.commands.judge import run

        prompt = judge_workspace / "p.yaml"
        schema = judge_workspace / "s.json"
        _write_prompt_template(prompt, "ctx={ctx}")
        _write_schema(schema, _conformant_schema())
        _register_stub("ok", {"decision": "allow", "rationale": "ok"})

        rc = run(
            prompt_template=str(prompt),
            schema=str(schema),
            inputs=[f"ctx=@{judge_workspace / 'absent.txt'}"],
            llm="ok",
            call_site="phase-advance",
        )
        assert rc != 0
        captured = capsys.readouterr()
        msg = (captured.err + captured.out).lower()
        assert "absent" in msg or "not found" in msg or "no such" in msg


# ---------------------------------------------------------------------------
# AC-UNIT-001: unknown --llm and --call-site fail loudly
# ---------------------------------------------------------------------------


class TestUnknownLlmFailsLoudly:
    def test_unknown_llm_id_exits_nonzero(
        self, judge_workspace: Path, capsys: pytest.CaptureFixture
    ):
        from atdd.coach.commands.judge import run

        prompt = judge_workspace / "p.yaml"
        schema = judge_workspace / "s.json"
        _write_prompt_template(prompt, "x")
        _write_schema(schema, _conformant_schema())

        # No stub registered for "ghost".
        rc = run(
            prompt_template=str(prompt),
            schema=str(schema),
            inputs=[],
            llm="ghost",
            call_site="phase-advance",
        )
        assert rc != 0
        captured = capsys.readouterr()
        msg = (captured.err + captured.out).lower()
        assert "ghost" in msg or "unknown" in msg or "registr" in msg

    def test_unknown_call_site_exits_nonzero(
        self, judge_workspace: Path, capsys: pytest.CaptureFixture
    ):
        from atdd.coach.commands.judge import run

        prompt = judge_workspace / "p.yaml"
        schema = judge_workspace / "s.json"
        _write_prompt_template(prompt, "x")
        _write_schema(schema, _conformant_schema())
        _register_stub("ok", {"decision": "allow", "rationale": "ok"})

        rc = run(
            prompt_template=str(prompt),
            schema=str(schema),
            inputs=[],
            llm="ok",
            call_site="not-a-real-site",
        )
        assert rc != 0
        captured = capsys.readouterr()
        msg = (captured.err + captured.out).lower()
        assert "call_site" in msg or "call-site" in msg or "not-a-real-site" in msg


# ---------------------------------------------------------------------------
# AC-UNIT-001: argparse surface conformance
# ---------------------------------------------------------------------------


class TestArgparseSurface:
    """Parser exposes the §5.5 flag surface."""

    def test_parser_accepts_full_flag_surface(self, tmp_path: Path):
        from atdd.coach.commands.judge import parse_cli

        cfg = parse_cli([
            "--prompt-template", "p.yaml",
            "--schema", "s.json",
            "--inputs", "sha=abc", "ctx=@file.txt",
            "--llm", "stub-ok",
            "--call-site", "phase-advance",
        ])
        assert cfg.prompt_template == "p.yaml"
        assert cfg.schema == "s.json"
        assert cfg.inputs == ["sha=abc", "ctx=@file.txt"]
        assert cfg.llm == "stub-ok"
        assert cfg.call_site == "phase-advance"

    def test_parser_omitting_required_prompt_template_errors(self):
        from atdd.coach.commands.judge import parse_cli

        with pytest.raises(SystemExit):
            parse_cli([
                "--schema", "s.json",
                "--call-site", "phase-advance",
            ])

    def test_parser_omitting_required_schema_errors(self):
        from atdd.coach.commands.judge import parse_cli

        with pytest.raises(SystemExit):
            parse_cli([
                "--prompt-template", "p.yaml",
                "--call-site", "phase-advance",
            ])

    def test_parser_omitting_required_call_site_errors(self):
        from atdd.coach.commands.judge import parse_cli

        with pytest.raises(SystemExit):
            parse_cli([
                "--prompt-template", "p.yaml",
                "--schema", "s.json",
            ])
