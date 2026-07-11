# URN: test:integration-hardening:coach-graph-aware-orchestration:E007-INTEGRATION-001-wave-planning-uses-graph
# Acceptance: acc:integration-hardening:E007-INTEGRATION-001-wave-planning-uses-graph
# WMBT: wmbt:integration-hardening:E007
# Phase: RED
# Layer: integration
# Runtime: python
"""E007-INTEGRATION-001 — ``build_plan`` derives wave order from the wagon
consume graph.

When issue N1 lives in wagon-A and issue N2 lives in wagon-B, and wagon-B
consumes from wagon-A, the two issues must land in separate waves even though
neither issue carries an explicit per-issue dependency label. Today's
``build_plan`` reads only body-parsed dependency labels, so both issues fall
into Wave 0 — this test fails until the wagon graph is wired in.

RED expectation: with no dep labels, current ``build_plan`` yields a single
wave ``[[9001, 9002]]``; ``waves[1]`` raises ``IndexError`` → test fails.
"""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]


def _scaffold_repo(tmp_path: Path) -> None:
    """Minimal ATDD repo: two issues mapped to two wagons (wagon-b consumes from
    wagon-a). #1270 Slice G: the issue→wagon mapping is seeded straight into the
    State Store (the ``.atdd/manifest.yaml`` mirror is deleted)."""
    from atdd.state.db import connect, init_state_store
    from atdd.state.manifest_import import GITHUB_PROVIDER, WORK_ITEM_KIND
    from atdd.state.store import StateStore

    (tmp_path / ".atdd").mkdir(parents=True)
    db = init_state_store(db_path=tmp_path / ".atdd" / "state" / "state.sqlite")
    conn = connect(db)
    try:
        store = StateStore(conn)
        for slug, number, wagon in (
            ("upstream-issue", 9001, "wagon-a"),
            ("downstream-issue", 9002, "wagon-b"),
        ):
            store.objects.upsert(
                slug, WORK_ITEM_KIND, state="PLANNED",
                data={"issue_number": number, "type": "implementation",
                      "train": "0002-test-train", "wagon": wagon,
                      "feature": "test-feature"},
            )
            store.external_refs.link(slug, GITHUB_PROVIDER, "issue", str(number),
                                     data={"source": "test-seed"})
    finally:
        conn.close()
    plan = tmp_path / "plan"
    (plan / "wagon_a").mkdir(parents=True)
    (plan / "wagon_a" / "_wagon_a.yaml").write_text(
        textwrap.dedent("""\
            wagon: wagon-a
            urn: "wagon:wagon-a"
            name: "Upstream Wagon"
            description: "Produces a contract consumed downstream."
            theme: commons
            features: []
            produce:
              - name: commons:test:upstream-contract
                to: external
            consume: []
        """)
    )
    (plan / "wagon_b").mkdir(parents=True)
    (plan / "wagon_b" / "_wagon_b.yaml").write_text(
        textwrap.dedent("""\
            wagon: wagon-b
            urn: "wagon:wagon-b"
            name: "Downstream Wagon"
            description: "Consumes the upstream contract."
            theme: commons
            features: []
            produce: []
            consume:
              - name: commons:test:upstream-contract
                from: wagon:wagon-a
        """)
    )


def _fake_fetch_issue(num: int) -> dict:
    """Offline stand-in for the GitHub fetch — no dependency labels in body."""
    return {
        "number": num,
        "title": f"issue {num}",
        "body": "## Problem\nNo explicit dependency labels here.\n",
    }


def test_downstream_wagon_issue_held_in_later_wave(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _scaffold_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "atdd.coach.commands.wave_planning.fetch_issue",
        _fake_fetch_issue,
    )

    from atdd.coach.commands.coach import build_plan, compute_waves

    plan = build_plan([9001, 9002])
    waves = compute_waves(plan)

    # wagon-b consumes from wagon-a → #9002 must wait one wave behind #9001.
    assert waves[0] == [9001], f"Wave 0 should hold only the upstream issue, got {waves}"
    assert waves[1] == [9002], f"Wave 1 should hold the downstream issue, got {waves}"
    assert 9002 not in waves[0], "downstream issue must not share Wave 0 with its upstream"
