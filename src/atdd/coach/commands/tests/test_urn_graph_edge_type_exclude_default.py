# URN: test:coach:urn_cli:edge_type_exclude_default
"""
Regression test for issue #287 Phase 3: ``atdd repo graph --root <urn>`` must
apply the correct default ``edge_type_exclude`` per root family so the CLI
matches the programmatic get_subgraph(edge_type_exclude=...) contract.

Rules pinned here:
  - Root ``train:*``           → no exclusion (TRAIN_STEP edges visible; journey mode).
  - Root ``wagon:*``           → exclude {TRAIN_STEP} (structural, no cross-train leak).
  - Root ``feature:*``/other   → exclude {TRAIN_STEP}.
  - No root at all             → no exclusion applied at this layer
                                 (full-graph renders already include TRAIN_STEP for trains).

These tests exercise the CLI surface via ``URNCommand.graph``, stubbing the
graph builder so the assertion is purely on the default the CLI passes down.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from atdd.coach.commands.urn import URNCommand, _default_edge_type_exclude
from atdd.coach.utils.graph.graph_builder import EdgeType


# ---------------------------------------------------------------------------
# Helper contract: _default_edge_type_exclude per root family
# ---------------------------------------------------------------------------


def test_default_exclude_train_root_is_none():
    assert _default_edge_type_exclude("train:0205-renewal-before-deadline") is None


def test_default_exclude_wagon_root_hides_train_step():
    assert _default_edge_type_exclude("wagon:stage-request") == {EdgeType.TRAIN_STEP}


def test_default_exclude_feature_root_hides_train_step():
    assert _default_edge_type_exclude("feature:stage:prep") == {EdgeType.TRAIN_STEP}


def test_default_exclude_no_root_hides_train_step():
    """
    No root URN is equivalent to structural consumption — any caller that
    eventually asks for a subgraph of the returned data should not have
    TRAIN_STEP edges pre-baked.
    """
    assert _default_edge_type_exclude(None) == {EdgeType.TRAIN_STEP}


def test_default_exclude_unknown_family_hides_train_step():
    assert _default_edge_type_exclude("contract:mything") == {EdgeType.TRAIN_STEP}


# ---------------------------------------------------------------------------
# CLI-level: URNCommand.graph passes the correct default to build_from_root
# ---------------------------------------------------------------------------


def _make_cmd_with_mock_builder() -> tuple[URNCommand, MagicMock]:
    """
    Construct a URNCommand whose graph_builder is a mock, bypassing the
    __init__ that would scan a real repo. We install both build and
    build_from_root on the mock and stub the returned graph's .to_json /
    .to_agent_summary so the method can run to completion.
    """
    cmd = URNCommand.__new__(URNCommand)
    mock_builder = MagicMock()
    fake_graph = MagicMock()
    fake_graph.to_json.return_value = "{}"
    fake_graph.to_dot.return_value = "digraph {}"
    fake_graph.to_agent_summary.return_value = {}
    mock_builder.build.return_value = fake_graph
    mock_builder.build_from_root.return_value = fake_graph
    cmd.graph_builder = mock_builder
    return cmd, mock_builder


def test_graph_cli_with_train_root_passes_no_exclude():
    cmd, builder = _make_cmd_with_mock_builder()

    rc = cmd.graph(root="train:0205-renewal-before-deadline")

    assert rc == 0
    builder.build_from_root.assert_called_once()
    kwargs = builder.build_from_root.call_args.kwargs
    assert kwargs.get("edge_type_exclude") is None


def test_graph_cli_with_wagon_root_excludes_train_step():
    cmd, builder = _make_cmd_with_mock_builder()

    rc = cmd.graph(root="wagon:stage-request")

    assert rc == 0
    builder.build_from_root.assert_called_once()
    kwargs = builder.build_from_root.call_args.kwargs
    assert kwargs.get("edge_type_exclude") == {EdgeType.TRAIN_STEP}


def test_graph_cli_with_feature_root_excludes_train_step():
    cmd, builder = _make_cmd_with_mock_builder()

    rc = cmd.graph(root="feature:stage:prep")

    assert rc == 0
    kwargs = builder.build_from_root.call_args.kwargs
    assert kwargs.get("edge_type_exclude") == {EdgeType.TRAIN_STEP}


def test_graph_cli_without_root_does_not_call_build_from_root():
    """
    When no root is supplied the CLI calls plain ``build()`` — the filter
    belongs to subgraph extraction, not full-graph rendering.
    """
    cmd, builder = _make_cmd_with_mock_builder()

    rc = cmd.graph(root=None)

    assert rc == 0
    builder.build.assert_called_once()
    builder.build_from_root.assert_not_called()
