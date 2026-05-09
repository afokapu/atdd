# URN: test:judge-ambiguous-decisions:judge-and-issue-review:D001-UNIT-002-fail-open-matches-config
# Acceptance: acc:judge-ambiguous-decisions:D001-UNIT-002-fail-open-matches-config
# WMBT: wmbt:judge-ambiguous-decisions:D001
# Phase: RED
# Layer: application
"""D001-UNIT-002 — `coach.judge.fail_open` config governs LLM-unavailable
behavior.

Per spec §6.9: when the LLM is unavailable (network error, auth failure,
unknown model id), `atdd judge` follows the config:

    fail_open=false (default)
        Return a deterministic conservative-fallback response (e.g.
        decision=escalate for retry-vs-escalate; decision=block for
        reviewer concern), include a `fail_open_used=true` marker,
        and exit 0.

    fail_open=true
        Return no response and exit non-zero with a clear
        LLM-unavailable error.

Both behaviors append exactly one line to `judgments.jsonl` carrying
the same `call_site` identifier so the audit trail does not lose the
attempt; stdout-vs-stderr exit-code semantics differ but the audit
record is identical in shape.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

pytestmark = [pytest.mark.platform]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _conformant_schema() -> dict:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "required": ["decision"],
        "properties": {
            "decision": {"type": "string"},
        },
    }


def _write_prompt_template(path: Path, body: str = "x") -> None:
    path.write_text(yaml.safe_dump({"prompt": body}))


def _write_schema(path: Path, schema: dict) -> None:
    path.write_text(json.dumps(schema))


def _write_coach_config(repo_root: Path, judge_block: dict) -> None:
    cfg = {"version": "1.0", "coach": {"judge": judge_block}}
    (repo_root / ".atdd" / "config.yaml").write_text(yaml.safe_dump(cfg))


@pytest.fixture
def judge_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".atdd").mkdir()
    (tmp_path / ".atdd" / "config.yaml").write_text(yaml.safe_dump({"version": "1.0"}))
    return tmp_path


def _register_unavailable(name: str = "down") -> None:
    """Install a stub that always raises LLMUnavailable."""
    from atdd.coach.commands import judge as judge_mod

    def _factory():
        class _Down:
            def invoke(self, prompt: str):
                raise judge_mod.LLMUnavailable("network down")
        return _Down()

    judge_mod.register_llm_client(name, _factory)


@pytest.fixture(autouse=True)
def _reset_registry():
    from atdd.coach.commands import judge as judge_mod

    snapshot = dict(judge_mod.LLM_REGISTRY)
    judge_mod.LLM_REGISTRY.clear()
    yield
    judge_mod.LLM_REGISTRY.clear()
    judge_mod.LLM_REGISTRY.update(snapshot)


# ---------------------------------------------------------------------------
# AC-UNIT-002: fail_open=false returns conservative fallback, exit 0
# ---------------------------------------------------------------------------


class TestFailOpenFalseReturnsConservativeFallback:
    def test_default_config_means_fail_open_false(
        self, judge_workspace: Path, capsys: pytest.CaptureFixture
    ):
        """Empty config → fail_open=false (the spec §10 default)."""
        from atdd.coach.commands.judge import run

        # Default config: no judge.fail_open override → false.
        prompt = judge_workspace / "p.yaml"
        schema = judge_workspace / "s.json"
        _write_prompt_template(prompt)
        _write_schema(schema, _conformant_schema())
        _register_unavailable("down")

        rc = run(
            prompt_template=str(prompt),
            schema=str(schema),
            inputs=[],
            llm="down",
            call_site="escalation",
        )
        assert rc == 0
        out = capsys.readouterr().out
        printed = json.loads(out.strip().splitlines()[-1])
        assert printed.get("fail_open_used") is True
        # 'escalation' call site → conservative fallback is escalate.
        assert printed["decision"] == "escalate"

    def test_explicit_fail_open_false_returns_fallback(
        self, judge_workspace: Path, capsys: pytest.CaptureFixture
    ):
        from atdd.coach.commands.judge import run

        _write_coach_config(judge_workspace, {"fail_open": False})
        prompt = judge_workspace / "p.yaml"
        schema = judge_workspace / "s.json"
        _write_prompt_template(prompt)
        _write_schema(schema, _conformant_schema())
        _register_unavailable("down")

        rc = run(
            prompt_template=str(prompt),
            schema=str(schema),
            inputs=[],
            llm="down",
            call_site="review-disposition",
        )
        assert rc == 0
        out = capsys.readouterr().out
        printed = json.loads(out.strip().splitlines()[-1])
        assert printed.get("fail_open_used") is True
        # 'review-disposition' (reviewer concern) → conservative is block.
        assert printed["decision"] == "block"

    @pytest.mark.parametrize("call_site,expected", [
        ("phase-advance", "block"),
        ("violation-suppression", "block"),
        ("correction-injection", "escalate"),
        ("review-disposition", "block"),
        ("escalation", "escalate"),
        ("merge-readiness", "block"),
    ])
    def test_each_call_site_has_deterministic_fallback(
        self, judge_workspace: Path, capsys: pytest.CaptureFixture,
        call_site: str, expected: str,
    ):
        from atdd.coach.commands.judge import run

        prompt = judge_workspace / "p.yaml"
        schema = judge_workspace / "s.json"
        _write_prompt_template(prompt)
        _write_schema(schema, _conformant_schema())
        _register_unavailable("down")

        rc = run(
            prompt_template=str(prompt),
            schema=str(schema),
            inputs=[],
            llm="down",
            call_site=call_site,
        )
        assert rc == 0
        out = capsys.readouterr().out
        printed = json.loads(out.strip().splitlines()[-1])
        assert printed["decision"] == expected
        assert printed["fail_open_used"] is True


# ---------------------------------------------------------------------------
# AC-UNIT-002: fail_open=true exits non-zero with clear error
# ---------------------------------------------------------------------------


class TestFailOpenTrueExitsNonZero:
    def test_fail_open_true_exits_nonzero_on_unavailable(
        self, judge_workspace: Path, capsys: pytest.CaptureFixture
    ):
        from atdd.coach.commands.judge import run

        _write_coach_config(judge_workspace, {"fail_open": True})
        prompt = judge_workspace / "p.yaml"
        schema = judge_workspace / "s.json"
        _write_prompt_template(prompt)
        _write_schema(schema, _conformant_schema())
        _register_unavailable("down")

        rc = run(
            prompt_template=str(prompt),
            schema=str(schema),
            inputs=[],
            llm="down",
            call_site="phase-advance",
        )
        assert rc != 0
        captured = capsys.readouterr()
        combined = (captured.err + captured.out).lower()
        assert "unavailable" in combined or "llm" in combined

    def test_fail_open_true_does_not_print_response(
        self, judge_workspace: Path, capsys: pytest.CaptureFixture
    ):
        from atdd.coach.commands.judge import run

        _write_coach_config(judge_workspace, {"fail_open": True})
        prompt = judge_workspace / "p.yaml"
        schema = judge_workspace / "s.json"
        _write_prompt_template(prompt)
        _write_schema(schema, _conformant_schema())
        _register_unavailable("down")

        rc = run(
            prompt_template=str(prompt),
            schema=str(schema),
            inputs=[],
            llm="down",
            call_site="phase-advance",
        )
        assert rc != 0
        out = capsys.readouterr().out.strip()
        # No JSON response document on stdout.
        if out:
            for line in out.splitlines():
                line = line.strip()
                if not line:
                    continue
                # If anything was printed, it must NOT parse as a judgment payload.
                try:
                    parsed = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue
                assert "decision" not in parsed


# ---------------------------------------------------------------------------
# AC-UNIT-002: both behaviors log the same call_site to judgments.jsonl
# ---------------------------------------------------------------------------


class TestBothBehaviorsLogCallSite:
    def _read_jsonl(self, path: Path) -> list[dict]:
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]

    def test_fail_open_false_logs_call_site(self, judge_workspace: Path):
        from atdd.coach.commands.judge import run

        prompt = judge_workspace / "p.yaml"
        schema = judge_workspace / "s.json"
        _write_prompt_template(prompt)
        _write_schema(schema, _conformant_schema())
        _register_unavailable("down")

        rc = run(
            prompt_template=str(prompt),
            schema=str(schema),
            inputs=[],
            llm="down",
            call_site="merge-readiness",
        )
        assert rc == 0

        log = judge_workspace / ".atdd" / "runtime" / "coach" / "judgments.jsonl"
        records = self._read_jsonl(log)
        assert len(records) == 1
        assert records[0]["call_site"] == "merge-readiness"
        assert records[0]["outcome"] == "fail_open_fallback"

    def test_fail_open_true_logs_call_site(self, judge_workspace: Path):
        from atdd.coach.commands.judge import run

        _write_coach_config(judge_workspace, {"fail_open": True})
        prompt = judge_workspace / "p.yaml"
        schema = judge_workspace / "s.json"
        _write_prompt_template(prompt)
        _write_schema(schema, _conformant_schema())
        _register_unavailable("down")

        rc = run(
            prompt_template=str(prompt),
            schema=str(schema),
            inputs=[],
            llm="down",
            call_site="merge-readiness",
        )
        assert rc != 0

        log = judge_workspace / ".atdd" / "runtime" / "coach" / "judgments.jsonl"
        records = self._read_jsonl(log)
        assert len(records) == 1
        assert records[0]["call_site"] == "merge-readiness"
        assert records[0]["outcome"] == "llm_unavailable"
