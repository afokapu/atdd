# URN: test:judge-ambiguous-decisions:judge-and-issue-review:D006-UNIT-001-issue-body-injected-inline
# Acceptance: acc:judge-ambiguous-decisions:D006-UNIT-001-issue-body-injected-inline
# WMBT: wmbt:judge-ambiguous-decisions:D006
# Phase: RED
# Layer: application
"""D006-UNIT-001 — `atdd issue review` fetches the issue body host-side
and injects it inline into every review pass prompt.

Issue #721: the review pass prompt currently carries only the issue
*number* (`_render_prompt` takes `issue_number`, never a body). A
sandboxed review LLM has no `gh`, so it returns a natural-language
permission request and the JSON parser fails. The fix: the host fetches
the body once and splices it into each pass prompt, so the review LLM
never needs `gh`.

RED expectations (fail until GREEN ships):
  * The fetched issue body appears verbatim in every pass prompt.
  * The host fetches the body exactly once, not once per pass.
  * A sandboxed stub LLM that errors when handed only an issue number
    still returns a structured response once the body is injected.

The host-side fetch seam is `issue_review._fetch_issue_body(issue_number)`;
these tests monkeypatch it (`raising=False`) so the GREEN coder owns the
real `gh issue view` call but the test controls the body content.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml


pytestmark = [pytest.mark.platform]


_ISSUE_BODY_SENTINEL = (
    "SENTINEL-ISSUE-BODY :: ## Problem Statement\n"
    "The review sub-LLM cannot access the issue body."
)


def _conformant_dimensions() -> dict:
    """Stub LLM payload — every dimension `pass` with no findings."""
    return {
        "dimensions": {
            "systemic":          {"verdict": "pass", "findings": []},
            "ambiguities":       {"verdict": "pass", "findings": []},
            "gap":               {"verdict": "pass", "findings": []},
            "regression":        {"verdict": "pass", "findings": []},
            "comprehensiveness": {"verdict": "pass", "findings": []},
        }
    }


class _CapturingClient:
    """Records every prompt it is invoked with, returns a conformant payload."""

    def __init__(self, sink: list[str]) -> None:
        self._sink = sink

    def invoke(self, prompt: str):
        self._sink.append(prompt)
        return _conformant_dimensions()


class _SandboxedClient:
    """Models a sandboxed review LLM with no `gh`.

    If the prompt does not already carry the issue body, the LLM cannot
    review it and raises `LLMUnavailable` (the real-world symptom is a
    prose 'I need permission to fetch issue #N' reply that fails the JSON
    parser). With the body inline it returns a structured response.
    """

    def __init__(self, sink: list[str]) -> None:
        self._sink = sink

    def invoke(self, prompt: str):
        from atdd.coach.commands.judge import LLMUnavailable

        self._sink.append(prompt)
        if _ISSUE_BODY_SENTINEL not in prompt:
            raise LLMUnavailable(
                "no JSON found in response (first 200 chars): "
                "'I need permission to fetch the issue from GitHub.'"
            )
        return _conformant_dimensions()


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


@pytest.fixture
def fetch_spy(monkeypatch: pytest.MonkeyPatch):
    """Install `issue_review._fetch_issue_body` returning a known body.

    `raising=False` so the test does not error before the GREEN seam
    exists; the count then drives the 'fetched once' assertion.
    """
    from atdd.coach.commands import issue_review

    calls: list[int] = []

    def _fake(issue_number: int) -> str:
        calls.append(issue_number)
        return _ISSUE_BODY_SENTINEL

    monkeypatch.setattr(issue_review, "_fetch_issue_body", _fake, raising=False)
    return calls


def _register_capturing(names: list[str], sink: list[str]) -> None:
    from atdd.coach.commands import judge as judge_mod

    for name in names:
        judge_mod.register_llm_client(name, lambda: _CapturingClient(sink))


def test_issue_body_appears_in_every_pass_prompt(
    review_workspace: Path, fetch_spy: list[int]
):
    from atdd.coach.commands.issue_review import run

    prompts: list[str] = []
    _register_capturing(["claude-haiku", "gpt-5-mini"], prompts)

    rc = run(issue_number=721, passes=2, llms=["claude-haiku", "gpt-5-mini"])

    assert rc == 0
    assert len(prompts) == 2
    for prompt in prompts:
        assert _ISSUE_BODY_SENTINEL in prompt, (
            "review pass prompt must carry the fetched issue body inline"
        )


def test_issue_body_fetched_once_not_once_per_pass(
    review_workspace: Path, fetch_spy: list[int]
):
    from atdd.coach.commands.issue_review import run

    prompts: list[str] = []
    _register_capturing(["claude-haiku", "gpt-5-mini", "gemini-flash"], prompts)

    run(
        issue_number=721,
        passes=3,
        llms=["claude-haiku", "gpt-5-mini", "gemini-flash"],
    )

    assert fetch_spy == [721], (
        "the host must fetch the issue body exactly once, not once per pass"
    )


def test_sandboxed_llm_with_no_gh_still_returns_structured_response(
    review_workspace: Path, fetch_spy: list[int]
):
    from atdd.coach.commands import judge as judge_mod
    from atdd.coach.commands.issue_review import run

    prompts: list[str] = []
    for name in ("claude-haiku", "gpt-5-mini"):
        judge_mod.register_llm_client(name, lambda: _SandboxedClient(prompts))

    rc = run(issue_number=721, passes=2, llms=["claude-haiku", "gpt-5-mini"])

    assert rc == 0, (
        "a sandboxed review LLM must succeed once the host injects the "
        "issue body — it should never need `gh` itself"
    )
