# URN: test:govern-lifecycle:deprecate-issue-create-alias:E061-UNIT-001-create-by-slug-warns-and-still-routes
# Acceptance: acc:govern-lifecycle:E061-UNIT-001-create-by-slug-warns-and-still-routes
# WMBT: wmbt:govern-lifecycle:E061
# Phase: GREEN
# Layer: backend.unit
# Assertion: behavioral
"""E061-UNIT-001 — `atdd issue <slug>` create-by-slug warns and still routes.

The `atdd issue <slug>` CLI dispatch is the create-by-slug surface. #1272 made
`atdd author issue` the store-first canonical create sharing the same
`work_item_writer`; this acceptance pins that the legacy alias now emits a
**stderr** deprecation warning naming `atdd author issue` while STILL routing
to the shared create path (`IssueLifecycle.create` is invoked with the slug),
so the alias signposts the canonical command without breaking. The warning
goes to stderr, never stdout, so it does not pollute a command's payload. Part
of the `atdd issue` decommission (#1349); prerequisite #1272.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from atdd import cli

pytestmark = [pytest.mark.coach]


def test_e061_unit_001_create_by_slug_warns_and_still_routes(monkeypatch, capsys):
    calls = {"slugs": []}

    class _RecordingLifecycle:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def create(self, slug, **kwargs) -> int:
            calls["slugs"].append(slug)
            return 0

        # Defensive: the dispatch should never fall through to enter()/transition().
        def __getattr__(self, name):  # pragma: no cover - guard
            return MagicMock()

    # The dispatch imports IssueLifecycle from its module at call time.
    monkeypatch.setattr(
        "atdd.coach.commands.issue_lifecycle.IssueLifecycle", _RecordingLifecycle
    )
    monkeypatch.setattr(
        cli.sys,
        "argv",
        ["atdd", "issue", "demo-deprecation-alias", "--no-branch", "--no-dup-check"],
    )

    rc = cli.main()
    captured = capsys.readouterr()

    # The alias still routes to the shared create path.
    assert rc == 0
    assert calls["slugs"] == ["demo-deprecation-alias"], (
        "the create-by-slug dispatch must still route to IssueLifecycle.create"
    )

    # It emits a deprecation warning naming the canonical command, to stderr.
    assert "author issue" in captured.err, (
        "the create-by-slug dispatch must point operators to `atdd author issue` "
        f"on stderr; stderr was:\n{captured.err!r}"
    )
    assert "deprecat" in captured.err.lower()
    assert "author issue" not in captured.out, (
        "the deprecation notice must go to stderr, not stdout"
    )
