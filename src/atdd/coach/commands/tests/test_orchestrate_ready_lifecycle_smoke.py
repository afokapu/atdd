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

import pytest
import yaml

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


class _FakeGithubClient:
    def __init__(self, parent_number: int):
        self.parent_number = parent_number
        self.created_issues: List[Dict] = []
        self.sub_issue_links: List[tuple] = []
        self._n = 9000

    def list_sub_issues(self, parent_number: int):
        return []

    def create_issue(self, title, body, labels=None):
        self._n += 1
        self.created_issues.append({"number": self._n, "title": title})
        return self._n

    def add_sub_issue(self, parent_number, sub_number):
        self.sub_issue_links.append((parent_number, sub_number))


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
    fake = _FakeGithubClient(parent_number=500)
    monkeypatch.setattr(manager, "_get_github_client", lambda: fake)

    created = manager.sync_wmbts(500)

    assert created == 3
    created_titles = {issue["title"] for issue in fake.created_issues}
    assert all(
        any(f":{wid}" in title for title in created_titles)
        for wid in ("D001", "D002", "D003")
    )
    assert len(fake.sub_issue_links) == 3
    assert all(parent == 500 for parent, _ in fake.sub_issue_links)
