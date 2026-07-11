# URN: test:integration-hardening:coach-spawn-wiring:E003-INTEGRATION-001-graph-helper-matches-spliced-content
# Acceptance: acc:integration-hardening:E003-INTEGRATION-001-graph-helper-matches-spliced-content
# WMBT: wmbt:integration-hardening:E003
# Phase: RED
# Layer: integration
"""E003-INTEGRATION-001 — `atdd repo graph --issue N --format prompt` produces
the exact text that _render_launch_prompt splices into the launch prompt for
the same issue N, proving the spawn pipeline is not reimplementing the graph
walk.

The test:
  1. Scaffolds a minimal repo with manifest + wagon + trains files.
  2. Calls the build_issue_architecture_context() helper directly (same
     function the spawn pipeline calls) to get the spliced section.
  3. Invokes `atdd repo graph --issue N --format prompt` via subprocess and
     captures stdout.
  4. Asserts stdout == the helper's return value (exact string match).
  5. Asserts exit code == 0.
"""
from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

# Point subprocess at the source tree so local edits are visible.
# parents[4] from tests/ → commands/ → coach/ → atdd/ → src/
_SRC_ROOT = Path(__file__).resolve().parents[4]

pytestmark = [pytest.mark.platform]


def _make_repo(tmp_path: Path, wagon_slug: str) -> Path:
    """Scaffold a minimal ATDD repo under tmp_path.

    #1270 Slice G: the ``.atdd/manifest.yaml`` mirror is deleted — the issue→wagon
    mapping the graph helper reads is seeded straight into the State Store.
    """
    from atdd.state.db import connect, init_state_store
    from atdd.state.manifest_import import GITHUB_PROVIDER, WORK_ITEM_KIND
    from atdd.state.store import StateStore

    (tmp_path / ".atdd").mkdir(parents=True)
    db = init_state_store(db_path=tmp_path / ".atdd" / "state" / "state.sqlite")
    conn = connect(db)
    try:
        store = StateStore(conn)
        store.objects.upsert(
            "integration-test-issue", WORK_ITEM_KIND, state="RED",
            data={"issue_number": 950, "type": "implementation",
                  "train": "0002-test-train", "wagon": wagon_slug,
                  "feature": "test-feature"},
        )
        store.external_refs.link("integration-test-issue", GITHUB_PROVIDER, "issue", "950",
                                 data={"source": "test-seed"})
    finally:
        conn.close()

    wagon_dir = tmp_path / "plan" / wagon_slug.replace("-", "_")
    wagon_dir.mkdir(parents=True)

    wagon_yaml = wagon_dir / f"_{wagon_slug.replace('-', '_')}.yaml"
    wagon_yaml.write_text(
        textwrap.dedent(f"""\
            wagon: {wagon_slug}
            urn: "wagon:{wagon_slug}"
            name: "Integration Test Wagon"
            description: "Wagon for integration testing."
            theme: commons
            features:
              - urn: "feature:{wagon_slug}:test-feature"
        """)
    )

    for wmbt_id in ["X001", "X002"]:
        (wagon_dir / f"{wmbt_id}.yaml").write_text(
            textwrap.dedent(f"""\
                urn: "wmbt:{wagon_slug}:{wmbt_id}"
                step: "execute"
                direction: "minimize"
                dimension: "time"
                object_of_control: "test-object"
                context_clarifier: "test context"
                lens: "functional.effectiveness"
                statement: "statement for {wmbt_id}"
                acceptances: []
            """)
        )

    trains_yaml = tmp_path / "plan" / "_trains.yaml"
    trains_yaml.write_text(
        textwrap.dedent(f"""\
            trains:
              0-commons:
                00-nominal:
                  - train_id: "0002-test-train"
                    title: "Test Train"
                    path: "plan/_trains/0002-test-train.yaml"
                    wagons:
                      - alpha-wagon
                      - {wagon_slug}
                      - omega-wagon
        """)
    )

    return tmp_path


def test_graph_helper_output_matches_subprocess(tmp_path: Path) -> None:
    """INTEGRATION-001: CLI output equals helper return value."""
    repo = _make_repo(tmp_path, "int-test-wagon")

    env = os.environ.copy()
    env["ATDD_REPO_ROOT"] = str(repo)
    existing_pp = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{_SRC_ROOT}{os.pathsep}{existing_pp}" if existing_pp else str(_SRC_ROOT)

    # Get output from the helper function directly
    from atdd.coach.commands.issue_graph import build_issue_architecture_context

    helper_output = build_issue_architecture_context(950, repo_root=repo)

    assert helper_output is not None, (
        "build_issue_architecture_context must return a non-None string when wagon exists"
    )
    assert helper_output.startswith("## Architecture context"), (
        "Helper output must start with '## Architecture context'"
    )

    # Get output from the CLI subprocess
    result = subprocess.run(
        [sys.executable, "-m", "atdd", "repo", "graph", "--issue", "950", "--format", "prompt"],
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.returncode == 0, (
        f"atdd repo graph --issue 950 --format prompt exited {result.returncode}; "
        f"stderr: {result.stderr}"
    )

    cli_output = result.stdout.rstrip("\n")
    helper_stripped = helper_output.rstrip("\n")

    assert cli_output == helper_stripped, (
        f"CLI output does not match helper output.\n"
        f"CLI:\n{cli_output!r}\n\nHelper:\n{helper_stripped!r}"
    )
