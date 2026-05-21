# URN: test:dispatch-ux-defaults-and-primer:Y004-SMOKE-001-real-template-render-excludes-sibling-deps-from-merge-wait
# Acceptance: acc:dispatch-ux-defaults-and-primer:Y004-SMOKE-001-real-template-render-excludes-sibling-deps-from-merge-wait
# WMBT: wmbt:dispatch-ux-defaults-and-primer:Y004
# Phase: SMOKE
# Layer: smoke
# Runtime: python
# Assertion: behavioral
"""Y004-SMOKE-001 — the full render path produces a launch prompt where the
merge-wait loop's search filter contains only prereq dep numbers and sibling
dep numbers appear only in the non-blocking context block.

Exercises the real ``build_context()`` + ``render()`` path (no mocks of the
parsing or rendering logic). ``fetch_issue`` is monkeypatched to return a
realistic ATDD-formatted body so the test does not require network access.

Opt-in: set ``ATDD_RUN_SMOKE=1`` to run.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

pytestmark = [
    pytest.mark.platform,
    pytest.mark.smoke,
    pytest.mark.skipif(
        not os.environ.get("ATDD_RUN_SMOKE"),
        reason="opt-in SMOKE test — set ATDD_RUN_SMOKE=1 to run",
    ),
]

# A realistic ATDD issue body with a mixed-class Dependencies section.
# #500 and #501 are prereqs; #600 and #601 are siblings.
_FIXTURE_BODY = """\
## Issue Metadata

| Field | Value |
|-------|-------|
| Date | `2026-05-21` |
| Status | `PLANNED` |
| Branch | `chore/smoke-fixture-branch` |
| Train | `T-SMOKE` |
| Feature | smoke-fixture |

---

## Scope

### Dependencies

- #500 (prereq) — infrastructure that must land first
- #501 (merged) — already closed, safe to consume
- #600 (sibling) — parallel work in the same release wave
- #601 (sibling, open) — another sibling filed the same day

---

## Validation

### Gate Tests

| ID | Check |
|----|-------|
| GT-001 | `grep -c "def smoke_fixture" src/atdd/smoke.py` |
"""

_PREREQ_NUMS = {"#500", "#501"}
_SIBLING_NUMS = {"#600", "#601"}


def _extract_search_arg(rendered: str) -> str:
    """Return the value of --search "..." from the while-true loop, or ''."""
    m = re.search(r'--search\s+"([^"]*)"', rendered)
    return m.group(1) if m else ""


def _extract_parallel_block(rendered: str) -> str:
    """Return the text of the 'Parallel siblings' context block, or ''."""
    m = re.search(
        r"\*\*Parallel siblings.*?\*\*(.+?)(?=\n\n|\Z)", rendered, re.DOTALL
    )
    return m.group(0) if m else ""


class TestRealTemplateRenderExcludesSiblingDepsFromMergeWait:
    """Full build_context + render path with a realistic ATDD fixture body."""

    def _render(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> str:
        from atdd.coach.commands.session_template import build_context, render

        ctx = build_context(
            issue_number=42,
            body=_FIXTURE_BODY,
            title="smoke-fixture",
            worktree_path=str(tmp_path),
        )
        return render(ctx)

    def test_prereq_numbers_in_merge_wait_search(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        out = self._render(monkeypatch, tmp_path)
        search_arg = _extract_search_arg(out)
        for num in _PREREQ_NUMS:
            assert num in search_arg, (
                f"prereq {num} not found in --search arg: {search_arg!r}"
            )

    def test_sibling_numbers_absent_from_merge_wait_search(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        out = self._render(monkeypatch, tmp_path)
        search_arg = _extract_search_arg(out)
        for num in _SIBLING_NUMS:
            assert num not in search_arg, (
                f"sibling {num} leaked into --search arg: {search_arg!r}"
            )

    def test_sibling_numbers_appear_in_parallel_context_block(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        out = self._render(monkeypatch, tmp_path)
        parallel_block = _extract_parallel_block(out)
        assert parallel_block, "Expected a 'Parallel siblings' context block"
        for num in _SIBLING_NUMS:
            assert num in parallel_block, (
                f"sibling {num} missing from parallel context block"
            )

    def test_while_loop_present_for_prereqs(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        out = self._render(monkeypatch, tmp_path)
        assert "while true" in out, "Expected merge-wait loop for prereq deps"

    def test_run_with_output_file_writes_correct_content(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """run() --output path exercises the full CLI entry point."""
        from unittest.mock import patch

        from atdd.coach.commands.session_template import run

        output_path = tmp_path / "launch_prompt.txt"
        with patch(
            "atdd.coach.commands.session_template.fetch_issue",
            return_value={"number": 42, "title": "smoke-fixture", "body": _FIXTURE_BODY},
        ):
            rc = run(issue_number=42, output=output_path)

        assert rc == 0
        content = output_path.read_text()
        search_arg = _extract_search_arg(content)
        for num in _PREREQ_NUMS:
            assert num in search_arg
        for num in _SIBLING_NUMS:
            assert num not in search_arg
