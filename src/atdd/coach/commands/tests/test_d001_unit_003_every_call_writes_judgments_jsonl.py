# URN: test:judge-ambiguous-decisions:judge-and-issue-review:D001-UNIT-003-every-call-writes-judgments-jsonl
# Acceptance: acc:judge-ambiguous-decisions:D001-UNIT-003-every-call-writes-judgments-jsonl
# WMBT: wmbt:judge-ambiguous-decisions:D001
# Phase: RED
# Layer: application
"""D001-UNIT-003 — every `atdd judge` invocation writes exactly one line
to `.atdd/runtime/coach/judgments.jsonl`.

Per spec §6.9 / §C0: the judgments JSONL is append-only, one record
per invocation, and every record validates against
`coach-judgment.schema.json` (frozen by #483). Records carry
`judgment_id`, `timestamp`, `call_site`, `inputs_hash`, `response`
(or null), `cached`, and `outcome` ∈ {ok, schema_violation,
llm_unavailable, fail_open_fallback}.

Inputs are hashed by default; full inputs go to a gitignored cache
only when `coach.judge.log_full_inputs=true` (the §10 schema name for
the cache_inputs concept in spec §6.9).
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
        "additionalProperties": False,
        "properties": {
            "decision": {"type": "string", "enum": ["allow", "block", "escalate"]},
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


def _register_stub(name: str, payload):
    from atdd.coach.commands import judge as judge_mod

    def _factory():
        class _S:
            def invoke(self, prompt: str):
                if isinstance(payload, Exception):
                    raise payload
                return payload
        return _S()

    judge_mod.register_llm_client(name, _factory)


def _register_unavailable(name: str = "down") -> None:
    from atdd.coach.commands import judge as judge_mod

    def _factory():
        class _D:
            def invoke(self, prompt: str):
                raise judge_mod.LLMUnavailable("network")
        return _D()

    judge_mod.register_llm_client(name, _factory)


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _judgments_log(repo_root: Path) -> Path:
    return repo_root / ".atdd" / "runtime" / "coach" / "judgments.jsonl"


@pytest.fixture(autouse=True)
def _reset_registry():
    from atdd.coach.commands import judge as judge_mod

    snapshot = dict(judge_mod.LLM_REGISTRY)
    judge_mod.LLM_REGISTRY.clear()
    yield
    judge_mod.LLM_REGISTRY.clear()
    judge_mod.LLM_REGISTRY.update(snapshot)


def _judgment_schema() -> dict:
    here = Path(__file__).resolve()
    # Walk up to repo root (find pyproject.toml), then schemas dir.
    for parent in here.parents:
        if (parent / "pyproject.toml").exists():
            schema_path = parent / "src" / "atdd" / "coach" / "schemas" / "coach-judgment.schema.json"
            if schema_path.exists():
                return json.loads(schema_path.read_text())
    raise FileNotFoundError("coach-judgment.schema.json not found")


# ---------------------------------------------------------------------------
# AC-UNIT-003: exactly one line per invocation
# ---------------------------------------------------------------------------


class TestExactlyOneLinePerInvocation:
    def test_success_path_appends_one_line(self, judge_workspace: Path):
        from atdd.coach.commands.judge import run

        prompt = judge_workspace / "p.yaml"
        schema = judge_workspace / "s.json"
        _write_prompt_template(prompt)
        _write_schema(schema, _conformant_schema())
        _register_stub("ok", {"decision": "allow"})

        rc = run(
            prompt_template=str(prompt),
            schema=str(schema),
            inputs=[],
            llm="ok",
            call_site="phase-advance",
        )
        assert rc == 0
        records = _read_jsonl(_judgments_log(judge_workspace))
        assert len(records) == 1
        assert records[0]["outcome"] == "ok"

    def test_schema_violation_appends_one_line(self, judge_workspace: Path):
        from atdd.coach.commands.judge import run

        prompt = judge_workspace / "p.yaml"
        schema = judge_workspace / "s.json"
        _write_prompt_template(prompt)
        _write_schema(schema, _conformant_schema())
        _register_stub("violator", {"decision": "wat"})  # unknown enum

        rc = run(
            prompt_template=str(prompt),
            schema=str(schema),
            inputs=[],
            llm="violator",
            call_site="phase-advance",
        )
        assert rc != 0
        records = _read_jsonl(_judgments_log(judge_workspace))
        assert len(records) == 1
        assert records[0]["outcome"] == "schema_violation"

    def test_llm_unavailable_with_fail_open_true_appends_one_line(
        self, judge_workspace: Path
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
        records = _read_jsonl(_judgments_log(judge_workspace))
        assert len(records) == 1
        assert records[0]["outcome"] == "llm_unavailable"

    def test_fail_open_fallback_appends_one_line(self, judge_workspace: Path):
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
            call_site="phase-advance",
        )
        assert rc == 0
        records = _read_jsonl(_judgments_log(judge_workspace))
        assert len(records) == 1
        assert records[0]["outcome"] == "fail_open_fallback"

    def test_multiple_invocations_each_append_one_line(
        self, judge_workspace: Path
    ):
        from atdd.coach.commands.judge import run

        prompt = judge_workspace / "p.yaml"
        schema = judge_workspace / "s.json"
        _write_prompt_template(prompt)
        _write_schema(schema, _conformant_schema())
        _register_stub("ok", {"decision": "allow"})

        for _ in range(3):
            rc = run(
                prompt_template=str(prompt),
                schema=str(schema),
                inputs=[],
                llm="ok",
                call_site="phase-advance",
            )
            assert rc == 0

        records = _read_jsonl(_judgments_log(judge_workspace))
        assert len(records) == 3


# ---------------------------------------------------------------------------
# AC-UNIT-003: each line validates against coach-judgment.schema.json
# ---------------------------------------------------------------------------


class TestRecordsValidateAgainstFrozenSchema:
    def test_success_record_is_schema_conformant(self, judge_workspace: Path):
        import jsonschema

        from atdd.coach.commands.judge import run

        prompt = judge_workspace / "p.yaml"
        schema = judge_workspace / "s.json"
        _write_prompt_template(prompt)
        _write_schema(schema, _conformant_schema())
        _register_stub("ok", {"decision": "allow"})

        run(
            prompt_template=str(prompt),
            schema=str(schema),
            inputs=[],
            llm="ok",
            call_site="phase-advance",
        )
        records = _read_jsonl(_judgments_log(judge_workspace))
        assert len(records) == 1
        validator = jsonschema.Draft202012Validator(_judgment_schema())
        validator.validate(records[0])

    def test_schema_violation_record_is_schema_conformant(self, judge_workspace: Path):
        import jsonschema

        from atdd.coach.commands.judge import run

        prompt = judge_workspace / "p.yaml"
        schema = judge_workspace / "s.json"
        _write_prompt_template(prompt)
        _write_schema(schema, _conformant_schema())
        _register_stub("v", {"decision": "wat"})

        run(
            prompt_template=str(prompt),
            schema=str(schema),
            inputs=[],
            llm="v",
            call_site="phase-advance",
        )
        records = _read_jsonl(_judgments_log(judge_workspace))
        assert len(records) == 1
        jsonschema.Draft202012Validator(_judgment_schema()).validate(records[0])

    def test_unavailable_record_is_schema_conformant(self, judge_workspace: Path):
        import jsonschema

        from atdd.coach.commands.judge import run

        _write_coach_config(judge_workspace, {"fail_open": True})
        prompt = judge_workspace / "p.yaml"
        schema = judge_workspace / "s.json"
        _write_prompt_template(prompt)
        _write_schema(schema, _conformant_schema())
        _register_unavailable("down")

        run(
            prompt_template=str(prompt),
            schema=str(schema),
            inputs=[],
            llm="down",
            call_site="phase-advance",
        )
        records = _read_jsonl(_judgments_log(judge_workspace))
        assert len(records) == 1
        jsonschema.Draft202012Validator(_judgment_schema()).validate(records[0])

    def test_fallback_record_is_schema_conformant(self, judge_workspace: Path):
        import jsonschema

        from atdd.coach.commands.judge import run

        prompt = judge_workspace / "p.yaml"
        schema = judge_workspace / "s.json"
        _write_prompt_template(prompt)
        _write_schema(schema, _conformant_schema())
        _register_unavailable("down")

        run(
            prompt_template=str(prompt),
            schema=str(schema),
            inputs=[],
            llm="down",
            call_site="phase-advance",
        )
        records = _read_jsonl(_judgments_log(judge_workspace))
        assert len(records) == 1
        jsonschema.Draft202012Validator(_judgment_schema()).validate(records[0])


# ---------------------------------------------------------------------------
# AC-UNIT-003: required fields and shape
# ---------------------------------------------------------------------------


class TestRecordCarriesRequiredFields:
    def test_record_has_required_top_level_keys(self, judge_workspace: Path):
        from atdd.coach.commands.judge import run

        prompt = judge_workspace / "p.yaml"
        schema = judge_workspace / "s.json"
        _write_prompt_template(prompt)
        _write_schema(schema, _conformant_schema())
        _register_stub("ok", {"decision": "allow"})

        run(
            prompt_template=str(prompt),
            schema=str(schema),
            inputs=["sha=abc"],
            llm="ok",
            call_site="phase-advance",
        )
        records = _read_jsonl(_judgments_log(judge_workspace))
        rec = records[0]
        for key in ("judgment_id", "timestamp", "call_site",
                    "inputs_hash", "response", "cached", "outcome"):
            assert key in rec, f"missing {key}"
        assert isinstance(rec["judgment_id"], str) and rec["judgment_id"]
        assert isinstance(rec["inputs_hash"], str) and rec["inputs_hash"]
        assert rec["call_site"] == "phase-advance"
        assert rec["cached"] is False
        assert rec["outcome"] == "ok"

    def test_outcome_enum_values_are_used(self, judge_workspace: Path):
        from atdd.coach.commands.judge import run

        prompt = judge_workspace / "p.yaml"
        schema = judge_workspace / "s.json"
        _write_prompt_template(prompt)
        _write_schema(schema, _conformant_schema())

        # Success
        _register_stub("ok", {"decision": "allow"})
        run(prompt_template=str(prompt), schema=str(schema), inputs=[],
            llm="ok", call_site="phase-advance")

        # Schema violation
        _register_stub("violator", {"decision": "bogus"})
        run(prompt_template=str(prompt), schema=str(schema), inputs=[],
            llm="violator", call_site="phase-advance")

        # Fail-open fallback (default config = fail_open=false)
        _register_unavailable("down1")
        run(prompt_template=str(prompt), schema=str(schema), inputs=[],
            llm="down1", call_site="phase-advance")

        records = _read_jsonl(_judgments_log(judge_workspace))
        outcomes = [r["outcome"] for r in records]
        assert outcomes == ["ok", "schema_violation", "fail_open_fallback"]


# ---------------------------------------------------------------------------
# AC-UNIT-003: inputs hashing (default hashed; full only when log_full_inputs)
# ---------------------------------------------------------------------------


class TestInputsAreHashedByDefault:
    def test_default_log_does_not_contain_raw_input_values(
        self, judge_workspace: Path
    ):
        from atdd.coach.commands.judge import run

        prompt = judge_workspace / "p.yaml"
        schema = judge_workspace / "s.json"
        _write_prompt_template(prompt, "sha={sha}")
        _write_schema(schema, _conformant_schema())
        _register_stub("ok", {"decision": "allow"})

        run(
            prompt_template=str(prompt),
            schema=str(schema),
            inputs=["sha=THIS-SECRET-VALUE"],
            llm="ok",
            call_site="phase-advance",
        )

        log_text = _judgments_log(judge_workspace).read_text()
        assert "THIS-SECRET-VALUE" not in log_text
        # Hash field is populated.
        rec = json.loads(log_text.strip().splitlines()[0])
        assert rec["inputs_hash"]
        assert rec["inputs_hash"] != "THIS-SECRET-VALUE"

    def test_inputs_hash_is_deterministic(self, judge_workspace: Path):
        from atdd.coach.commands.judge import run

        prompt = judge_workspace / "p.yaml"
        schema = judge_workspace / "s.json"
        _write_prompt_template(prompt, "x")
        _write_schema(schema, _conformant_schema())
        _register_stub("ok", {"decision": "allow"})

        for _ in range(2):
            run(
                prompt_template=str(prompt),
                schema=str(schema),
                inputs=["sha=abc123"],
                llm="ok",
                call_site="phase-advance",
            )

        records = _read_jsonl(_judgments_log(judge_workspace))
        assert records[0]["inputs_hash"] == records[1]["inputs_hash"]

    def test_inputs_hash_differs_for_different_inputs(self, judge_workspace: Path):
        from atdd.coach.commands.judge import run

        prompt = judge_workspace / "p.yaml"
        schema = judge_workspace / "s.json"
        _write_prompt_template(prompt, "x")
        _write_schema(schema, _conformant_schema())
        _register_stub("ok", {"decision": "allow"})

        run(prompt_template=str(prompt), schema=str(schema),
            inputs=["sha=A"], llm="ok", call_site="phase-advance")
        run(prompt_template=str(prompt), schema=str(schema),
            inputs=["sha=B"], llm="ok", call_site="phase-advance")

        records = _read_jsonl(_judgments_log(judge_workspace))
        assert records[0]["inputs_hash"] != records[1]["inputs_hash"]


class TestFullInputsCacheIsGated:
    """Full inputs go to a gitignored cache only when the config opts in."""

    def test_log_full_inputs_false_writes_no_cache(self, judge_workspace: Path):
        from atdd.coach.commands.judge import run

        # Default = log_full_inputs=False.
        prompt = judge_workspace / "p.yaml"
        schema = judge_workspace / "s.json"
        _write_prompt_template(prompt, "x")
        _write_schema(schema, _conformant_schema())
        _register_stub("ok", {"decision": "allow"})

        run(prompt_template=str(prompt), schema=str(schema),
            inputs=["sha=abc"], llm="ok", call_site="phase-advance")

        records = _read_jsonl(_judgments_log(judge_workspace))
        cache_dir = judge_workspace / ".atdd" / "runtime" / "coach" / "inputs-cache"
        if cache_dir.exists():
            entries = list(cache_dir.rglob("*"))
            files = [p for p in entries if p.is_file()]
            assert files == [], (
                f"log_full_inputs=False must not write cache files; found {files}"
            )
        # And of course the inputs hash is present.
        assert records[0]["inputs_hash"]

    def test_log_full_inputs_true_writes_cache_keyed_by_hash(
        self, judge_workspace: Path
    ):
        from atdd.coach.commands.judge import run

        _write_coach_config(judge_workspace, {"log_full_inputs": True})
        prompt = judge_workspace / "p.yaml"
        schema = judge_workspace / "s.json"
        _write_prompt_template(prompt, "x")
        _write_schema(schema, _conformant_schema())
        _register_stub("ok", {"decision": "allow"})

        run(prompt_template=str(prompt), schema=str(schema),
            inputs=["sha=THE-SHA"], llm="ok", call_site="phase-advance")

        cache_dir = judge_workspace / ".atdd" / "runtime" / "coach" / "inputs-cache"
        assert cache_dir.exists()
        files = [p for p in cache_dir.rglob("*") if p.is_file()]
        assert files, "log_full_inputs=True must write at least one cache file"
        # The full input value lives in the cache, not in the audit log.
        cache_text = "\n".join(p.read_text() for p in files)
        assert "THE-SHA" in cache_text
        log_text = _judgments_log(judge_workspace).read_text()
        assert "THE-SHA" not in log_text

    def test_runtime_dir_is_gitignored(self, judge_workspace: Path):
        """`.atdd/runtime/` is a gitignored partition per runtime-layout.md."""
        # The runtime directory itself MUST live under .atdd/runtime/.
        log = _judgments_log(judge_workspace)
        # Trigger creation by running once.
        from atdd.coach.commands.judge import run

        prompt = judge_workspace / "p.yaml"
        schema = judge_workspace / "s.json"
        _write_prompt_template(prompt, "x")
        _write_schema(schema, _conformant_schema())
        _register_stub("ok", {"decision": "allow"})
        run(prompt_template=str(prompt), schema=str(schema),
            inputs=[], llm="ok", call_site="phase-advance")

        assert log.exists()
        # Path discipline: under .atdd/runtime/coach/.
        assert ".atdd/runtime/coach/judgments.jsonl" in str(log).replace("\\", "/")
