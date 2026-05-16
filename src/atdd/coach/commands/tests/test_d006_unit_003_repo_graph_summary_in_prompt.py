# URN: test:judge-ambiguous-decisions:judge-and-issue-review:D006-UNIT-003-repo-graph-summary-in-prompt
# Acceptance: acc:judge-ambiguous-decisions:D006-UNIT-003-repo-graph-summary-in-prompt
# WMBT: wmbt:judge-ambiguous-decisions:D006
# Phase: RED
# Layer: application
"""D006-UNIT-003 — `atdd issue review` injects an `atdd repo` graph
summary of the issue's neighborhood into every review pass prompt.

Issue #721 (Phase 2): the systemic review dimension scores
one-off-patch-vs-systemic-pattern against the issue text alone, with no
architecture context. The fix resolves the issue's wagon / feature /
sibling-WMBT neighborhood host-side (via
`issue_graph.build_issue_architecture_context`) and splices the
`## Architecture context` markdown summary into each pass prompt, with
the systemic dimension directed to ground its verdict in it.

RED expectations (fail until GREEN ships):
  * The graph summary appears in every pass prompt.
  * The systemic-dimension portion of the prompt is present alongside
    the graph summary so the reviewer can ground its verdict in it.
  * When the issue has no wagon the builder returns None and the prompt
    renders without the summary — no exception (graceful degrade).

The graph-builder seam is `build_issue_architecture_context`; these
tests monkeypatch it (`raising=False`) on both the `issue_graph`
producer module and the `issue_review` consumer module so the GREEN
coder may import it either way.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml


pytestmark = [pytest.mark.platform]


_GRAPH_SENTINEL = (
    "## Architecture context\n\n"
    "**Wagon:** `wagon:judge-ambiguous-decisions` — GRAPH-CONTEXT-SENTINEL\n"
    "**Sibling WMBTs in this wagon:**\n- `wmbt:judge-ambiguous-decisions:D005`"
)


def _conformant_dimensions() -> dict:
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
    def __init__(self, sink: list[str]) -> None:
        self._sink = sink

    def invoke(self, prompt: str):
        self._sink.append(prompt)
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


def _patch_graph_builder(monkeypatch: pytest.MonkeyPatch, return_value):
    """Patch `build_issue_architecture_context` on both candidate modules."""
    from atdd.coach.commands import issue_graph, issue_review

    def _fake(issue_number, *args, **kwargs):
        return return_value

    monkeypatch.setattr(
        issue_graph, "build_issue_architecture_context", _fake, raising=False
    )
    monkeypatch.setattr(
        issue_review, "build_issue_architecture_context", _fake, raising=False
    )


def _register_capturing(names: list[str], sink: list[str]) -> None:
    from atdd.coach.commands import judge as judge_mod

    for name in names:
        judge_mod.register_llm_client(name, lambda: _CapturingClient(sink))


def test_graph_summary_appears_in_every_pass_prompt(
    review_workspace: Path, monkeypatch: pytest.MonkeyPatch
):
    from atdd.coach.commands.issue_review import run

    _patch_graph_builder(monkeypatch, _GRAPH_SENTINEL)
    prompts: list[str] = []
    _register_capturing(["claude-haiku", "gpt-5-mini"], prompts)

    rc = run(issue_number=721, passes=2, llms=["claude-haiku", "gpt-5-mini"])

    assert rc == 0
    assert len(prompts) == 2
    for prompt in prompts:
        assert "GRAPH-CONTEXT-SENTINEL" in prompt, (
            "every review pass prompt must carry the `atdd repo` graph "
            "summary of the issue's neighborhood"
        )


def test_systemic_dimension_prompt_carries_graph_for_grounding(
    review_workspace: Path, monkeypatch: pytest.MonkeyPatch
):
    from atdd.coach.commands.issue_review import run

    _patch_graph_builder(monkeypatch, _GRAPH_SENTINEL)
    prompts: list[str] = []
    _register_capturing(["claude-haiku", "gpt-5-mini"], prompts)

    run(issue_number=721, passes=2, llms=["claude-haiku", "gpt-5-mini"])

    for prompt in prompts:
        lowered = prompt.lower()
        assert "architecture context" in lowered, (
            "the graph summary must be present so the systemic dimension "
            "can ground its verdict in real architecture"
        )
        assert "systemic" in lowered, (
            "the systemic dimension must remain part of the review prompt"
        )


def test_graceful_degrade_when_issue_has_no_wagon(
    review_workspace: Path, monkeypatch: pytest.MonkeyPatch
):
    from atdd.coach.commands.issue_review import run

    # Builder returns None — the issue has no wagon mapping.
    _patch_graph_builder(monkeypatch, None)
    prompts: list[str] = []
    _register_capturing(["claude-haiku", "gpt-5-mini"], prompts)

    rc = run(issue_number=999999, passes=2, llms=["claude-haiku", "gpt-5-mini"])

    assert rc == 0, "a wagon-less issue must still review cleanly"
    for prompt in prompts:
        assert "GRAPH-CONTEXT-SENTINEL" not in prompt, (
            "no graph summary should be spliced when the builder degrades to None"
        )
