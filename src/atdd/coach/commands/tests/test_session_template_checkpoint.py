"""
Unit tests for `atdd session-template <N> --from-checkpoint` (issue #378, Phase 3).

When the flag is set the renderer reads ``.atdd/worker-state-<N>.json`` and
inlines the checkpoint summary + open-files list into the launch prompt, so
that a `/clear`-and-reload cycle restores worker state without manual
re-briefing.

If no checkpoint exists, the command falls back to default behavior.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from atdd.coach.commands.session_template import (
    IssueContext,
    render,
    render_with_checkpoint,
)

pytestmark = [pytest.mark.platform]


SAMPLE_BODY = """## Issue Metadata

| Field | Value |
|-------|-------|
| Branch | feat/worker-context-window-management |
| Train | 0001-self-compliance-validate |
| Feature | worker-context-checkpoint |

## Scope

### Dependencies

- #344
"""


def _write_fixture_checkpoint(tmp_path: Path, issue: int, **overrides) -> Path:
    payload = {
        "issue": issue,
        "phase": "GREEN",
        "branch": "feat/worker-context-window-management",
        "last_commit": "deadbee",
        "summary": "RED tests landed; harness invoker subprocess wrapper passing on fixture",
        "open_files": [
            "src/atdd/coach/commands/checkpoint.py",
            "src/atdd/coach/schemas/worker-state.schema.json",
        ],
        "checkpointed_at": "2026-05-03T17:14:00Z",
        "ttl_seconds": 86400,
    }
    payload.update(overrides)
    target = tmp_path / ".atdd" / f"worker-state-{issue}.json"
    target.parent.mkdir(exist_ok=True, parents=True)
    target.write_text(json.dumps(payload))
    return target


# ---------------------------------------------------------------------------
# render_with_checkpoint
# ---------------------------------------------------------------------------


def test_render_with_checkpoint_includes_summary_and_open_files(tmp_path: Path):
    _write_fixture_checkpoint(tmp_path, 378)
    ctx = IssueContext(number=378, branch="feat/worker-context-window-management")
    rendered = render_with_checkpoint(ctx, root=tmp_path)

    # Original prompt content is preserved.
    assert "Issue #378" in rendered
    # Checkpoint-derived content appears.
    assert "RED tests landed" in rendered
    assert "src/atdd/coach/commands/checkpoint.py" in rendered
    assert "src/atdd/coach/schemas/worker-state.schema.json" in rendered
    # Phase from checkpoint surfaces somewhere in the body.
    assert "GREEN" in rendered


def test_render_with_checkpoint_falls_back_when_missing(tmp_path: Path):
    """No checkpoint file → identical to plain render() (no error, no inserted block)."""
    ctx = IssueContext(number=378, branch="feat/worker-context-window-management")
    rendered = render_with_checkpoint(ctx, root=tmp_path)
    plain = render(ctx)
    assert rendered == plain


def test_render_with_checkpoint_marks_checkpoint_block(tmp_path: Path):
    """The checkpoint section must be visually distinguishable so the worker
    knows the prompt was regenerated from a prior session, not the original."""
    _write_fixture_checkpoint(tmp_path, 378)
    ctx = IssueContext(number=378, branch="feat/worker-context-window-management")
    rendered = render_with_checkpoint(ctx, root=tmp_path)
    assert "Checkpoint" in rendered or "checkpoint" in rendered


# ---------------------------------------------------------------------------
# CLI runner integration
# ---------------------------------------------------------------------------


def test_run_with_from_checkpoint_invokes_renderer(tmp_path: Path, capsys):
    from atdd.coach.commands.session_template import run

    _write_fixture_checkpoint(tmp_path, 378)

    with patch(
        "atdd.coach.commands.session_template.fetch_issue",
        return_value={"number": 378, "title": "demo", "body": SAMPLE_BODY},
    ):
        rc = run(issue_number=378, from_checkpoint=True, root=tmp_path)
    captured = capsys.readouterr()
    assert rc == 0
    assert "RED tests landed" in captured.out
    assert "src/atdd/coach/commands/checkpoint.py" in captured.out


def test_run_without_from_checkpoint_renders_plain(tmp_path: Path, capsys):
    from atdd.coach.commands.session_template import run

    _write_fixture_checkpoint(tmp_path, 378)

    with patch(
        "atdd.coach.commands.session_template.fetch_issue",
        return_value={"number": 378, "title": "demo", "body": SAMPLE_BODY},
    ):
        rc = run(issue_number=378, from_checkpoint=False, root=tmp_path)
    captured = capsys.readouterr()
    assert rc == 0
    # Plain mode: checkpoint content does NOT appear.
    assert "RED tests landed" not in captured.out
