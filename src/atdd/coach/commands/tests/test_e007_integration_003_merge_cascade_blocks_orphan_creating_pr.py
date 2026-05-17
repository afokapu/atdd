# URN: test:integration-hardening:coach-graph-aware-orchestration:E007-INTEGRATION-003-merge-cascade-blocks-orphan-creating-pr
# Acceptance: acc:integration-hardening:E007-INTEGRATION-003-merge-cascade-blocks-orphan-creating-pr
# WMBT: wmbt:integration-hardening:E007
# Phase: RED
# Layer: integration
# Runtime: python
"""E007-INTEGRATION-003 — the merge cascade blocks an orphan-creating PR.

A pre-merge graph check inspects the tree a PR would produce. If the merged
tree would leave a declared URN with no resolving artifact (an orphan), the
cascade must NOT merge the PR: it reports the PR as BLOCKED and emits an
escalation naming the orphaned URN.

Intended API (the contract this RED test pins):
    merge_cascade.screen_merge_for_orphans(repo_root: Path) -> OrphanScreen
  where OrphanScreen carries:
    .blocked: bool             — True when a merge would orphan a URN
    .orphaned_urns: list[str]  — the URNs left without a resolving artifact
    .escalation: str | None    — escalation message naming the orphaned URN(s)

RED expectation: ``screen_merge_for_orphans`` / ``OrphanScreen`` do not exist
yet → ImportError.
"""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]


def _wagon_with_feature_ref(plan: Path, *, feature_file_present: bool) -> None:
    """Scaffold plan/wagon_c declaring feature:wagon-c:headline-feature.

    When ``feature_file_present`` is False the feature file is omitted, so the
    declared feature URN is orphaned — declared, no resolving artifact.
    """
    wagon_dir = plan / "wagon_c"
    (wagon_dir / "features").mkdir(parents=True)
    (wagon_dir / "_wagon_c.yaml").write_text(
        textwrap.dedent("""\
            wagon: wagon-c
            urn: "wagon:wagon-c"
            name: "Wagon C"
            description: "Wagon whose declared feature may be orphaned."
            theme: commons
            features:
              - urn: "feature:wagon-c:headline-feature"
            produce: []
            consume: []
        """)
    )
    if feature_file_present:
        (wagon_dir / "features" / "headline_feature.yaml").write_text(
            textwrap.dedent("""\
                urn: "feature:wagon-c:headline-feature"
                wagon: "wagon:wagon-c"
                description: "The headline feature, resolved."
                wmbts: []
            """)
        )


def test_orphan_creating_merge_is_blocked_and_escalated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = tmp_path / "plan"
    # Post-merge tree: feature URN declared but its file is missing → orphan.
    _wagon_with_feature_ref(plan, feature_file_present=False)
    monkeypatch.chdir(tmp_path)

    from atdd.coach.commands.merge_cascade import screen_merge_for_orphans

    screen = screen_merge_for_orphans(tmp_path)

    assert screen.blocked is True, "an orphan-creating merge must be blocked"
    assert "feature:wagon-c:headline-feature" in screen.orphaned_urns, (
        f"orphaned URN must be named, got {screen.orphaned_urns}"
    )
    assert screen.escalation, "an escalation message must be emitted"
    assert "feature:wagon-c:headline-feature" in screen.escalation, (
        "the escalation must name the orphaned URN"
    )


def test_clean_merge_is_not_blocked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = tmp_path / "plan"
    # Post-merge tree: feature URN declared AND its file present → no orphan.
    _wagon_with_feature_ref(plan, feature_file_present=True)
    monkeypatch.chdir(tmp_path)

    from atdd.coach.commands.merge_cascade import screen_merge_for_orphans

    screen = screen_merge_for_orphans(tmp_path)

    assert screen.blocked is False, "a merge that orphans nothing must not be blocked"
    assert screen.orphaned_urns == []
