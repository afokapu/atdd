# URN: test:judge-ambiguous-decisions:judge-and-issue-review:D006-UNIT-002-rule-binding-survives-malformed-payload
# Acceptance: acc:judge-ambiguous-decisions:D006-UNIT-002-rule-binding-survives-malformed-payload
# WMBT: wmbt:judge-ambiguous-decisions:D006
# Phase: RED
# Layer: application
"""D006-UNIT-002 — the review rule-binding path survives a malformed
LLM payload instead of crashing with an unhandled AttributeError.

Issue #721: `_resolve_finding_rule_ids` runs *before* the per-pass
schema validator. A payload that parses as JSON and carries a
`dimensions` key — but whose dimension value (or `findings` entry) is a
`str` where a `dict`/array is expected — crashes the rule-binding path
with `'str' object has no attribute 'get'`. The fix orders schema
validation before rule-binding (or type-guards it), so a malformed
shape is rejected as a clean, field-naming schema violation.

RED expectations (fail until GREEN ships):
  * The raw `'str' object has no attribute 'get'` AttributeError text
    never reaches the operator.
  * The failure is reported as a schema violation, not a "rule binding
    failed" Python traceback.
  * The diagnostic names the offending field so the failure is
    actionable.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml


pytestmark = [pytest.mark.platform]


# A payload that parses as JSON and HAS a `dimensions` key (so it clears
# `_build_pass_record`'s presence check) but whose dimension value is a
# bare string — the exact shape an LLM emits when it gives up and writes
# prose into the structured slot.
_MALFORMED_DIMENSION_IS_STR = {
    "dimensions": {
        "systemic":          "I cannot review this without the issue body.",
        "ambiguities":       "I cannot review this without the issue body.",
        "gap":               "I cannot review this without the issue body.",
        "regression":        "I cannot review this without the issue body.",
        "comprehensiveness": "I cannot review this without the issue body.",
    }
}

# A subtler malformation: dimension values are dicts, but `findings` is a
# string instead of an array — `_resolve_finding_rule_ids` then iterates
# the string's characters and calls `.get` on each char.
_MALFORMED_FINDINGS_IS_STR = {
    "dimensions": {
        "systemic":          {"verdict": "pass", "findings": "none"},
        "ambiguities":       {"verdict": "pass", "findings": "none"},
        "gap":               {"verdict": "pass", "findings": "none"},
        "regression":        {"verdict": "pass", "findings": "none"},
        "comprehensiveness": {"verdict": "pass", "findings": "none"},
    }
}


class _StubClient:
    def __init__(self, payload) -> None:
        self._payload = payload

    def invoke(self, prompt: str):
        return self._payload


@pytest.fixture(autouse=True)
def _reset_registry():
    from atdd.coach.commands import judge as judge_mod

    snapshot = dict(judge_mod.LLM_REGISTRY)
    judge_mod.LLM_REGISTRY.clear()
    yield
    judge_mod.LLM_REGISTRY.clear()
    judge_mod.LLM_REGISTRY.update(snapshot)


@pytest.fixture
def review_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".atdd").mkdir()
    (tmp_path / ".atdd" / "config.yaml").write_text(yaml.safe_dump({"version": "1.0"}))
    return tmp_path


def _register(payload) -> None:
    from atdd.coach.commands import judge as judge_mod

    for name in ("claude-haiku", "gpt-5-mini"):
        judge_mod.register_llm_client(name, lambda: _StubClient(payload))


def test_malformed_dimension_value_does_not_leak_attributeerror(
    review_workspace: Path, capsys: pytest.CaptureFixture
):
    from atdd.coach.commands.issue_review import run

    _register(_MALFORMED_DIMENSION_IS_STR)
    rc = run(issue_number=721, passes=2, llms=["claude-haiku", "gpt-5-mini"])

    assert rc != 0
    captured = capsys.readouterr()
    err = (captured.err + captured.out).lower()
    assert "has no attribute" not in err, (
        "the raw AttributeError must never reach the operator — a "
        "malformed payload should be rejected cleanly"
    )


def test_malformed_dimension_value_reported_as_schema_violation(
    review_workspace: Path, capsys: pytest.CaptureFixture
):
    from atdd.coach.commands.issue_review import run

    _register(_MALFORMED_DIMENSION_IS_STR)
    rc = run(issue_number=721, passes=2, llms=["claude-haiku", "gpt-5-mini"])

    assert rc != 0
    captured = capsys.readouterr()
    err = (captured.err + captured.out).lower()
    assert "schema" in err, (
        "a malformed-but-parseable payload must be rejected by schema "
        "validation, not crash the rule-binding path"
    )


def test_malformed_findings_value_does_not_leak_attributeerror(
    review_workspace: Path, capsys: pytest.CaptureFixture
):
    from atdd.coach.commands.issue_review import run

    _register(_MALFORMED_FINDINGS_IS_STR)
    rc = run(issue_number=721, passes=2, llms=["claude-haiku", "gpt-5-mini"])

    assert rc != 0
    captured = capsys.readouterr()
    err = (captured.err + captured.out).lower()
    assert "has no attribute" not in err, (
        "a string `findings` value must not crash the rule-binding loop"
    )


def test_malformed_payload_diagnostic_names_offending_field(
    review_workspace: Path, capsys: pytest.CaptureFixture
):
    from atdd.coach.commands.issue_review import run

    _register(_MALFORMED_DIMENSION_IS_STR)
    run(issue_number=721, passes=2, llms=["claude-haiku", "gpt-5-mini"])

    captured = capsys.readouterr()
    err = (captured.err + captured.out).lower()
    assert "dimensions" in err or "systemic" in err, (
        "the failure diagnostic must name the offending field so the "
        "operator can act on it"
    )
