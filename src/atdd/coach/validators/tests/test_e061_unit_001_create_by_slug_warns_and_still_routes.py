# URN: test:govern-lifecycle:deprecate-issue-create-alias:E061-UNIT-001-create-by-slug-warns-and-still-routes
# Acceptance: acc:govern-lifecycle:E061-UNIT-001-create-by-slug-warns-and-still-routes
# WMBT: wmbt:govern-lifecycle:E061
# Phase: GREEN
# Layer: backend.unit
# Assertion: behavioral
"""E061-UNIT-001 — create-by-slug points operators at the canonical create.

E061's object of control is *operators creating an issue via the deprecated
`atdd issue <slug>` path without being pointed to the canonical store-first
`atdd author issue`*. #1349 satisfied it with a stderr deprecation warning while
the alias still routed to `IssueLifecycle.create`.

C5b (#1309, umbrella #1303) satisfies it STRICTLY: the `atdd issue` CLI surface
is removed, so the alias cannot create at all — it fails loud and names the
canonical command. The acceptance is unchanged in intent (the operator is
pointed at `atdd author issue`); only the mechanism hardened from "warn and
route" to "refuse and redirect". Retargeted rather than deleted, so the
acceptance URN keeps a live binding (cf. the orphaned-acceptance defect #1395).
"""
from __future__ import annotations

import pytest

from atdd import cli

pytestmark = [pytest.mark.coach]


def test_e061_unit_001_create_by_slug_warns_and_still_routes(monkeypatch, capsys):
    monkeypatch.setattr(
        cli.sys,
        "argv",
        ["atdd", "issue", "demo-deprecation-alias", "--no-branch", "--no-dup-check"],
    )

    rc = cli.main()
    captured = capsys.readouterr()

    # The removed alias must refuse, never silently create.
    assert rc != 0, "the removed `atdd issue <slug>` alias must not exit 0"

    # It still points operators at the canonical store-first create, on stderr.
    assert "author issue" in captured.err, (
        "the removal guard must point operators to `atdd author issue` on "
        f"stderr; stderr was:\n{captured.err!r}"
    )
    assert "REMOVED" in captured.err
    assert "author issue" not in captured.out, (
        "the notice must go to stderr, not stdout"
    )
