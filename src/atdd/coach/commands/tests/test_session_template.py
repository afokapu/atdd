"""
Unit tests for `atdd session-template`.

SPEC-COACH-ORCH-0008: generates launch script with issue context, deps,
grep gates, stop conditions.
"""
from __future__ import annotations

import pytest

from atdd.coach.commands.session_template import (
    IssueContext,
    build_context,
    parse_dependencies,
    parse_grep_gates,
    parse_metadata,
    render,
)

pytestmark = [pytest.mark.platform]


SAMPLE_BODY = """## Issue Metadata

| Field | Value |
|-------|-------|
| Date | `2026-04-12` |
| Status | `INIT` |
| Branch | TBD <!-- fmt: feat/parallel-orchestration --> |
| Train | TBD |
| Feature | parallel-orchestration |

---

## Scope

### Dependencies

- #256 (PR-merge WMBT gate) — COMPLETE
- #123 — arbitrary helper
- `src/atdd/coach/commands/pr.py` — PRManager reuse

---

## Validation

### Gate Tests

| ID | Check |
|----|-------|
| GT-010 | `grep -c "def orchestrate" src/atdd/coach/commands/orchestrate.py` |
| GT-020 | `grep -rn "MultiplexerBackend" src/atdd/coach/utils/multiplexer.py` |
"""


def test_parse_metadata_extracts_branch_train_feature():
    meta = parse_metadata(SAMPLE_BODY)
    assert meta["Branch"] == "TBD"
    assert meta["Train"] == "TBD"
    assert meta["Feature"] == "parallel-orchestration"
    assert meta["Status"] == "INIT"


def test_parse_dependencies_picks_first_number_per_line():
    deps = parse_dependencies(SAMPLE_BODY)
    assert deps == ["#256", "#123"]


def test_parse_dependencies_falls_back_to_closes():
    body = "## Scope\n\n### Dependencies\n\n(none — uses free text)\n\nCloses #999\n"
    assert parse_dependencies(body) == ["#999"]


def test_parse_grep_gates_extracts_backtick_commands():
    gates = parse_grep_gates(SAMPLE_BODY)
    assert any("def orchestrate" in g for g in gates)
    assert any("MultiplexerBackend" in g for g in gates)


def test_build_context_populates_fields():
    ctx = build_context(
        issue_number=257,
        body=SAMPLE_BODY,
        title="parallel-orchestration",
        worktree_path="/tmp/feat-parallel-orchestration",
    )
    assert ctx.number == 257
    assert ctx.feature == "parallel-orchestration"
    assert ctx.dependencies == ["#256", "#123"]
    assert ctx.worktree_path == "/tmp/feat-parallel-orchestration"
    assert ctx.grep_gates


def test_render_substitutes_all_placeholders():
    ctx = IssueContext(
        number=42,
        title="demo",
        branch="feat/demo",
        train="T1",
        feature="demo-feature",
        dependencies=["#10", "#11"],
        grep_gates=['grep -c "def foo" src/foo.py'],
        worktree_path="/tmp/feat-demo",
    )
    out = render(ctx)
    assert "Issue #42" in out
    assert "feat/demo" in out
    assert "T1" in out
    assert "- #10" in out
    assert "- #11" in out
    assert "grep -c \"def foo\" src/foo.py" in out
    assert "{{" not in out  # all placeholders substituted


def test_render_handles_missing_dependencies_and_gates():
    ctx = IssueContext(number=1, branch="feat/x")
    out = render(ctx)
    assert "no dependencies declared" in out
    assert "no grep gates declared" in out
    assert "{{" not in out
