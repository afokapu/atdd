# URN: test:spawn-agents:E022-UNIT-001-graph-launch-prompt-emits-required-sections
# Acceptance: acc:spawn-agents:E022-UNIT-001-graph-launch-prompt-emits-required-sections
# WMBT: wmbt:spawn-agents:E022
# Phase: RED
# Layer: unit
"""E022-UNIT-001 — build_wagon_launch_prompt outputs all five required sections.

Given a minimal fixture wagon (2 features, 3 WMBTs, 1 produce, 1 consume,
1 sibling in the same train), build_wagon_launch_prompt must return a markdown
string containing:
  1. A wagon-description header (wagon name / URN)
  2. Both feature names
  3. All 3 WMBT IDs
  4. The produce contract name
  5. The sibling wagon name

Phase RED: fails with ImportError — build_wagon_launch_prompt does not yet exist
in atdd.coach.commands.issue_graph.
Phase GREEN: function exists and returns a well-formed section with all five
required items.
"""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

pytestmark = [pytest.mark.spawn_agents]

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

_WAGON_YAML = textwrap.dedent("""\
    wagon: test-wagon
    urn: "wagon:test-wagon"
    name: "Test Wagon"
    description: "A minimal wagon for E022 fixture tests"
    features:
      - urn: "feature:test-wagon:alpha-feature"
        description: "Alpha feature description"
      - urn: "feature:test-wagon:beta-feature"
        description: "Beta feature description"
    produce:
      - name: alpha-contract
        contract: null
        telemetry: null
        to: external
    consume:
      - name: beta-contract
        from: wagon:sibling-wagon
""")

_WMBT_E001_YAML = textwrap.dedent("""\
    urn: "wmbt:test-wagon:E001"
    step: "execute"
    direction: "minimize"
    dimension: "likelihood"
    object_of_control: "something-bad"
    statement: "minimize likelihood of something-bad by doing X"
    acceptances: []
""")

_WMBT_E002_YAML = textwrap.dedent("""\
    urn: "wmbt:test-wagon:E002"
    step: "execute"
    direction: "minimize"
    dimension: "quantity"
    object_of_control: "something-else"
    statement: "minimize quantity of something-else by doing Y"
    acceptances: []
""")

_WMBT_E003_YAML = textwrap.dedent("""\
    urn: "wmbt:test-wagon:E003"
    step: "execute"
    direction: "minimize"
    dimension: "likelihood"
    object_of_control: "a-third-thing"
    statement: "minimize likelihood of a-third-thing by doing Z"
    acceptances: []
""")

_TRAINS_YAML = textwrap.dedent("""\
    trains:
      active:
        train-0001:
          - train_id: "0001-test-train"
            wagons:
              - test-wagon
              - sibling-wagon
""")


def _build_fixture(tmp_path: Path) -> Path:
    """Scaffold a minimal test repo under tmp_path."""
    wagon_dir = tmp_path / "plan" / "test_wagon"
    wagon_dir.mkdir(parents=True)
    (wagon_dir / "_test_wagon.yaml").write_text(_WAGON_YAML)
    (wagon_dir / "E001.yaml").write_text(_WMBT_E001_YAML)
    (wagon_dir / "E002.yaml").write_text(_WMBT_E002_YAML)
    (wagon_dir / "E003.yaml").write_text(_WMBT_E003_YAML)
    trains = tmp_path / "plan" / "_trains.yaml"
    trains.write_text(_TRAINS_YAML)
    sibling_dir = tmp_path / "plan" / "sibling_wagon"
    sibling_dir.mkdir(parents=True)
    (sibling_dir / "_sibling_wagon.yaml").write_text(
        'wagon: sibling-wagon\nurn: "wagon:sibling-wagon"\nname: "Sibling Wagon"\n'
    )
    return tmp_path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_output_contains_wagon_description(tmp_path: Path) -> None:
    """Wagon description header (name or URN) must appear in the output."""
    from atdd.coach.commands.issue_graph import build_wagon_launch_prompt  # type: ignore[import]

    repo = _build_fixture(tmp_path)
    output = build_wagon_launch_prompt("test-wagon", repo_root=repo)
    assert output is not None, "build_wagon_launch_prompt returned None for valid wagon"
    assert "Test Wagon" in output or "wagon:test-wagon" in output, (
        "Expected wagon description header ('Test Wagon' or 'wagon:test-wagon') in output.\n"
        f"Got:\n{output}"
    )


def test_output_contains_both_feature_names(tmp_path: Path) -> None:
    """Both feature URNs or names must appear in the output."""
    from atdd.coach.commands.issue_graph import build_wagon_launch_prompt  # type: ignore[import]

    repo = _build_fixture(tmp_path)
    output = build_wagon_launch_prompt("test-wagon", repo_root=repo)
    assert output is not None
    assert "alpha-feature" in output, (
        "Expected 'alpha-feature' feature in output.\nGot:\n{output}"
    )
    assert "beta-feature" in output, (
        "Expected 'beta-feature' feature in output.\nGot:\n{output}"
    )


def test_output_contains_all_wmbt_ids(tmp_path: Path) -> None:
    """All 3 WMBT IDs (E001, E002, E003) must appear in the output."""
    from atdd.coach.commands.issue_graph import build_wagon_launch_prompt  # type: ignore[import]

    repo = _build_fixture(tmp_path)
    output = build_wagon_launch_prompt("test-wagon", repo_root=repo)
    assert output is not None
    for wmbt_id in ("E001", "E002", "E003"):
        assert wmbt_id in output, (
            f"Expected WMBT ID '{wmbt_id}' in output.\nGot:\n{output}"
        )


def test_output_contains_produce_contract_name(tmp_path: Path) -> None:
    """The produce contract name ('alpha-contract') must appear in the output."""
    from atdd.coach.commands.issue_graph import build_wagon_launch_prompt  # type: ignore[import]

    repo = _build_fixture(tmp_path)
    output = build_wagon_launch_prompt("test-wagon", repo_root=repo)
    assert output is not None
    assert "alpha-contract" in output, (
        "Expected produce contract 'alpha-contract' in output.\nGot:\n{output}"
    )


def test_output_contains_sibling_wagon_name(tmp_path: Path) -> None:
    """The sibling wagon name ('sibling-wagon' or 'Sibling Wagon') must appear."""
    from atdd.coach.commands.issue_graph import build_wagon_launch_prompt  # type: ignore[import]

    repo = _build_fixture(tmp_path)
    output = build_wagon_launch_prompt("test-wagon", repo_root=repo)
    assert output is not None
    assert "sibling-wagon" in output or "Sibling Wagon" in output, (
        "Expected sibling wagon name in output.\nGot:\n{output}"
    )
