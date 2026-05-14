# URN: test:govern-lifecycle:issue-template-substrate-completeness:E004-INTEGRATION-001-issue-creation-injects-graph
# Acceptance: acc:govern-lifecycle:E004-UNIT-004-build-architecture-context-for-wagon
# Acceptance: acc:govern-lifecycle:E004-INTEGRATION-001-issue-creation-injects-graph
# WMBT: wmbt:govern-lifecycle:E004
# Phase: GREEN
# Layer: integration
"""
Coverage for #682 Phase 2: `atdd issue <slug>` auto-injects graph context.

`IssueManager._inject_graph_context()` is the splice site; the placeholder
literal in PARENT-ISSUE-TEMPLATE.md is replaced by the output of
`build_architecture_context_for_wagon` at creation time. When the wagon
manifest is absent, a fallback message names the recovery path so creation
never hard-fails on missing plan/ artifacts.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from atdd.coach.commands.issue import (
    GRAPH_CONTEXT_PLACEHOLDER,
    GRAPH_CONTEXT_UNAVAILABLE,
    IssueManager,
)

pytestmark = [pytest.mark.platform]


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


@pytest.fixture
def repo_with_wagon(tmp_path: Path) -> Path:
    """Synthesize a target_dir containing a wagon manifest under plan/."""
    wagon_dir = tmp_path / "plan" / "graph_demo"
    _write(
        wagon_dir / "_graph_demo.yaml",
        "urn: wagon:graph-demo\n"
        "name: Graph Demo Wagon\n"
        "description: Substrate for the #682 fixture.\n"
        "features:\n"
        "  - urn: feature:graph-demo:substrate\n",
    )
    # Add a sibling WMBT so the renderer has something to list.
    _write(
        wagon_dir / "E001.yaml",
        "urn: wmbt:graph-demo:E001\n"
        "statement: Render the architecture context.\n",
    )
    return tmp_path


@pytest.fixture
def repo_without_wagon(tmp_path: Path) -> Path:
    """A target_dir with no plan/<slug>/_<slug>.yaml — triggers the fallback path."""
    (tmp_path / "plan").mkdir()
    return tmp_path


# ---------------------------------------------------------------------------
# Happy path — wagon manifest exists, real graph content gets spliced in
# ---------------------------------------------------------------------------


def test_injects_graph_context_when_wagon_manifest_present(repo_with_wagon: Path):
    manager = IssueManager(target_dir=repo_with_wagon)
    body = (
        "## Architecture\n\n"
        "### Graph Context\n\n"
        f"{GRAPH_CONTEXT_PLACEHOLDER}\n\n"
        "### Mirror Across Agents\n\n"
        "(table)\n"
    )

    rendered = manager._inject_graph_context(body, slug="graph-demo", train=None)

    assert GRAPH_CONTEXT_PLACEHOLDER not in rendered
    assert "wagon:graph-demo" in rendered
    assert "Graph Demo Wagon" in rendered
    assert "wmbt:graph-demo:E001" in rendered
    # The injected block must NOT introduce a nested H2 heading inside the H3.
    assert "## Architecture context" not in rendered


# ---------------------------------------------------------------------------
# Fallback path — wagon manifest absent, replace with recovery hint
# ---------------------------------------------------------------------------


def test_falls_back_when_wagon_manifest_missing(repo_without_wagon: Path):
    manager = IssueManager(target_dir=repo_without_wagon)
    body = (
        "## Architecture\n\n"
        "### Graph Context\n\n"
        f"{GRAPH_CONTEXT_PLACEHOLDER}\n\n"
    )

    rendered = manager._inject_graph_context(
        body, slug="never-registered-wagon", train=None,
    )

    assert GRAPH_CONTEXT_PLACEHOLDER not in rendered
    assert GRAPH_CONTEXT_UNAVAILABLE in rendered


# ---------------------------------------------------------------------------
# No-op path — placeholder already replaced (idempotent)
# ---------------------------------------------------------------------------


def test_no_op_when_placeholder_already_absent(repo_with_wagon: Path):
    manager = IssueManager(target_dir=repo_with_wagon)
    body = (
        "## Architecture\n\n"
        "### Graph Context\n\n"
        "Already-injected real content here.\n"
    )
    rendered = manager._inject_graph_context(body, slug="graph-demo", train=None)
    assert rendered == body


# ---------------------------------------------------------------------------
# Train propagation — train_id flows into the rendered context
# ---------------------------------------------------------------------------


def test_train_id_flows_into_rendered_context(tmp_path: Path):
    # Build a minimal wagon + a trains manifest that places the wagon in a train.
    wagon_dir = tmp_path / "plan" / "trained"
    _write(
        wagon_dir / "_trained.yaml",
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

    manager = IssueManager(target_dir=tmp_path)
    body = (
        "### Graph Context\n\n"
        f"{GRAPH_CONTEXT_PLACEHOLDER}\n"
    )
    rendered = manager._inject_graph_context(body, slug="trained", train="0001-demo")
    assert "0001-demo" in rendered
    assert "Trained Wagon" in rendered
