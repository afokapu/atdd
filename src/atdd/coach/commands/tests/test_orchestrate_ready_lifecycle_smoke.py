"""
SMOKE integration tests for #280 — orchestrate-ready issue lifecycle.

Proves the four write-time pieces play together when chained end-to-end:

    D001 render  ->  D003 drift walker  ->  D004 dep parser + wave walker
                                   \\
                                    ->  D002 sync-wmbts fixture flow

Each test builds a realistic fixture (tmp_path) and chains the public
helpers the way a real consumer repo would. No subprocess, no live gh —
these tests prove internal contracts and data shapes match.

Run: PYTHONPATH=src python3 -m pytest -q src/atdd/coach/commands/tests/test_orchestrate_ready_lifecycle_smoke.py -v
"""
from pathlib import Path
from typing import Dict, List
from unittest.mock import create_autospec

import pytest
import yaml

from atdd.coach.github import GitHubClient

pytestmark = [pytest.mark.platform]


def _make_manager(tmp_path: Path):
    (tmp_path / ".atdd").mkdir()
    (tmp_path / ".atdd" / "config.yaml").write_text(
        "github:\n  repo: afokapu/atdd\n  project_number: 1\n",
        encoding="utf-8",
    )
    from atdd.coach.commands.issue import IssueManager
    return IssueManager(target_dir=tmp_path)


def _fill_placeholders(body: str) -> str:
    from atdd.coach.commands.issue_template import PLACEHOLDER_STRINGS
    for placeholder in PLACEHOLDER_STRINGS:
        body = body.replace(placeholder, "concrete content")
    return body


# ---------------------------------------------------------------------------
# SMOKE: D001 rendered body flows cleanly through D003 drift walker
# ---------------------------------------------------------------------------


def test_smoke_rendered_body_passes_open_issue_compliance(tmp_path):
    """A body produced by _render_parent_body, after placeholder-filling,
    must produce zero drift when walked by _find_drift.

    This proves the write-time (D001) and read-time (D003) halves of the
    feature agree on the same data shape — the whole point of #280.
    """
    manager = _make_manager(tmp_path)
    body = manager._render_parent_body(
        slug="smoke-demo",
        issue_type="implementation",
        today="2026-04-14",
        train_display="0001-demo",
        archetypes_display="coach",
    )
    body = _fill_placeholders(body)

    from atdd.coach.validators.test_open_issue_compliance import _find_drift

    drift = _find_drift([{"number": 999, "body": body}])
    assert drift == [], (
        "Rendered body must be template-compliant straight out of _render_parent_body. "
        f"Drift: {drift}"
    )


def test_smoke_rendered_body_seeds_branch_field(tmp_path):
    """The rendered body contains a seeded Branch entry that matches
    ``{prefix}/{slug}`` for the configured issue type.
    """
    manager = _make_manager(tmp_path)
    body = manager._render_parent_body(
        slug="smoke-demo",
        issue_type="implementation",
        today="2026-04-14",
        train_display="0001-demo",
        archetypes_display="coach",
    )
    assert "| Branch | `feat/smoke-demo` |" in body


# ---------------------------------------------------------------------------
# SMOKE: D004 dependency parsing walks a chain of real-shape bodies
# ---------------------------------------------------------------------------


def test_smoke_dep_walker_chains_through_rendered_bodies(tmp_path):
    """A chain of three issues, where each body is produced by _render_parent_body
    and edited to list the next issue under ``### Dependencies``, resolves into
    a wave containing every issue in the chain.
    """
    manager = _make_manager(tmp_path)
    bodies: Dict[int, str] = {}

    for number, next_ref in ((100, "#101"), (101, "#102"), (102, None)):
        body = manager._render_parent_body(
            slug=f"issue-{number}",
            issue_type="implementation",
            today="2026-04-14",
            train_display="0001-demo",
            archetypes_display="coach",
        )
        if next_ref:
            body = body.replace(
                "### Dependencies\n\n- (list session or external dependencies)",
                f"### Dependencies\n\n- {next_ref}: downstream work",
                1,
            )
        bodies[number] = body

    from atdd.coach.commands.orchestrate_wave_walk import _compute_wave

    wave = _compute_wave(
        100,
        fetch_body=lambda n: bodies.get(n, ""),
        is_complete=lambda n: False,
    )
    assert sorted(wave) == [100, 101, 102]


# ---------------------------------------------------------------------------
# SMOKE: D002 sync-wmbts end-to-end against a full plan fixture
# ---------------------------------------------------------------------------


def _make_fake_github_client(parent_number: int):
    """Build a spec-enforced ``GitHubClient`` double via ``create_autospec``.

    Tests that previously referenced ``fake.created_issues`` now read the
    autospec's ``create_issue.call_args_list``; ``fake.sub_issue_links``
    becomes ``add_sub_issue.call_args_list``. Using autospec guards against
    the exact mock-drift failure mode that originated #304 — any method
    name not on the real ``GitHubClient`` raises ``AttributeError`` at
    call time.
    """
    client = create_autospec(GitHubClient, instance=True)
    client.get_sub_issues.return_value = []

    state = {"n": 9000}

    def _create_issue(title, body, labels=None):
        state["n"] += 1
        return state["n"]

    client.create_issue.side_effect = _create_issue
    client.add_sub_issue.return_value = None
    return client


def test_smoke_sync_wmbts_creates_subissues_from_full_plan_fixture(tmp_path, monkeypatch):
    """Given a fixture repo with a manifest session + feature YAML + three
    WMBT YAMLs, sync_wmbts creates three sub-issues linked to the parent.
    This is end-to-end: file system → discovery → client calls.
    """
    atdd_dir = tmp_path / ".atdd"
    atdd_dir.mkdir()
    (atdd_dir / "config.yaml").write_text(
        "github:\n  repo: afokapu/atdd\n  project_number: 1\n",
        encoding="utf-8",
    )
    (atdd_dir / "manifest.yaml").write_text(
        "version: '2.0'\n"
        "sessions:\n"
        "  - id: '500'\n"
        "    slug: smoke-feature\n"
        "    issue_number: 500\n"
        "    type: implementation\n"
        "    status: PLANNED\n"
        "    wagon: smoke-wagon\n"
        "    feature: 'feature:smoke-wagon:smoke-feature'\n",
        encoding="utf-8",
    )

    plan_dir = tmp_path / "plan" / "smoke_wagon"
    (plan_dir / "features").mkdir(parents=True)
    (plan_dir / "features" / "smoke_feature.yaml").write_text(
        yaml.safe_dump(
            {
                "urn": "feature:smoke-wagon:smoke-feature",
                "wagon": "wagon:smoke-wagon",
                "wmbts": [
                    "wmbt:smoke-wagon:D001",
                    "wmbt:smoke-wagon:D002",
                    "wmbt:smoke-wagon:D003",
                ],
            }
        ),
        encoding="utf-8",
    )
    for wid, statement in [
        ("D001", "minimize smoke drift alpha"),
        ("D002", "minimize smoke drift beta"),
        ("D003", "minimize smoke drift gamma"),
    ]:
        (plan_dir / f"{wid}.yaml").write_text(
            yaml.safe_dump(
                {
                    "urn": f"wmbt:smoke-wagon:{wid}",
                    "statement": statement,
                    "acceptances": [
                        {"identity": {"urn": f"acc:smoke-wagon:{wid}-UNIT-001-ex", "purpose": "ex"}}
                    ],
                }
            ),
            encoding="utf-8",
        )

    from atdd.coach.commands.issue import IssueManager

    manager = IssueManager(target_dir=tmp_path)
    fake = _make_fake_github_client(parent_number=500)
    monkeypatch.setattr(manager, "_get_github_client", lambda: fake)

    created = manager.sync_wmbts(500)

    assert created == 3
    created_titles = {
        call.kwargs.get("title") or call.args[0]
        for call in fake.create_issue.call_args_list
    }
    assert all(
        any(f":{wid}" in title for title in created_titles)
        for wid in ("D001", "D002", "D003")
    )
    assert fake.add_sub_issue.call_count == 3
    assert all(
        call.args[0] == 500 for call in fake.add_sub_issue.call_args_list
    )
