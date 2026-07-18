# URN: test:govern-lifecycle:issue-template-substrate-completeness:E004-UNIT-004-build-architecture-context-for-wagon
# Acceptance: acc:govern-lifecycle:E004-UNIT-004-build-architecture-context-for-wagon
# WMBT: wmbt:govern-lifecycle:E004
# Phase: GREEN
# Layer: unit
"""E004-UNIT-004 — `build_architecture_context_for_wagon` reads the wagon
manifest and renders the architecture-context section, degrading to None when
the wagon is absent.

Split out of the retired `test_issue_creation_injects_graph_context.py` (#1477).
That file drove this function *transitively*, through
`IssueManager._inject_graph_context` — a create-time splice on the mint path,
removed with it. The function itself is very much alive: `build_wagon_launch_prompt`
(and so `atdd repo graph --format prompt`) calls it. Its acceptance therefore
survives the decommission and is anchored here, directly.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from atdd.coach.commands.issue_graph import build_architecture_context_for_wagon

pytestmark = [pytest.mark.platform]


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


@pytest.fixture
def repo_with_wagon(tmp_path: Path) -> Path:
    """A repo root containing a wagon manifest and a sibling WMBT under plan/."""
    wagon_dir = tmp_path / "plan" / "graph_demo"
    _write(
        wagon_dir / "_graph_demo.yaml",
        "urn: wagon:graph-demo\n"
        "name: Graph Demo Wagon\n"
        "description: Substrate for the #682 fixture.\n"
        "features:\n"
        "  - urn: feature:graph-demo:substrate\n",
    )
    _write(
        wagon_dir / "E001.yaml",
        "urn: wmbt:graph-demo:E001\n"
        "statement: Render the architecture context.\n",
    )
    return tmp_path


def test_returns_populated_context_when_wagon_manifest_present(repo_with_wagon: Path):
    """Renders the wagon URN and its sibling WMBT URN."""
    rendered = build_architecture_context_for_wagon(
        "graph-demo", train_id=None, repo_root=repo_with_wagon,
    )

    assert rendered, "expected a populated architecture context, got a falsy value"
    assert "wagon:graph-demo" in rendered
    assert "wmbt:graph-demo:E001" in rendered


def test_returns_none_when_wagon_manifest_absent(tmp_path: Path):
    """Graceful degrade: no plan/<slug>/_<slug>.yaml → None, not an exception.

    The caller owns the fallback text; the renderer just declines.
    """
    (tmp_path / "plan").mkdir()

    rendered = build_architecture_context_for_wagon(
        "no-such-wagon", train_id=None, repo_root=tmp_path,
    )

    assert rendered is None


def test_train_id_flows_into_rendered_context(tmp_path: Path):
    """A wagon placed in a train renders that train's id."""
    _write(
        tmp_path / "plan" / "trained" / "_trained.yaml",
        "urn: wagon:trained\nname: Trained Wagon\n",
    )
    _write(
        tmp_path / "plan" / "_trains.yaml",
        "trains:\n"
        "  group_a:\n"
        "    section_a:\n"
        "      - train_id: 0001-demo\n"
        "        wagons:\n"
        "          - trained\n",
    )

    rendered = build_architecture_context_for_wagon(
        "trained", train_id="0001-demo", repo_root=tmp_path,
    )

    assert rendered
    assert "0001-demo" in rendered
    assert "Trained Wagon" in rendered
