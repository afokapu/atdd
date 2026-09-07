# URN: test:author-atdd-substrate:author-issue-body:C013-UNIT-002-path-shaped-prose-no-longer-earns-a-green
# Acceptance: acc:author-atdd-substrate:C013-UNIT-002-path-shaped-prose-no-longer-earns-a-green
# WMBT: wmbt:author-atdd-substrate:C013
# Phase: RED
# Layer: application
"""C013-UNIT-002 — the spellings observed earning CONFIRMED GONE.

Each of these PASSES `is_repo_relative_path`, so the shape guard cannot stop
them; only asking what the revision actually deleted can. `- None.` is included
as the control the shape guard already catches, and `atdd.extension.…` is the
live claim on #1531 — the one open issue whose green this change removes.
"""
from __future__ import annotations

import pytest

from atdd.coach.utils.artifact_claims import is_repo_relative_path

from .test_c013_unit_001_absence_alone_does_not_confirm_a_deletion import (  # noqa: F401
    repo_with_a_deletion,
    _resolves,
)

_PROSE = ["_None._", "n/a", "none/none", "atdd.extension.train-interlocking-enforcement"]


@pytest.mark.parametrize("claim", _PROSE)
def test_prose_does_not_resolve_as_a_deletion(repo_with_a_deletion, claim):
    repo, head = repo_with_a_deletion
    assert _resolves(repo, head, claim) is False, (
        f"{claim!r} was never deleted by this revision; resolving it as "
        "CONFIRMED GONE is prose earning a green"
    )


@pytest.mark.parametrize("claim", _PROSE)
def test_the_shape_guard_cannot_catch_these(claim):
    """Why the fix must live in the git question, not in a tighter regex."""
    assert is_repo_relative_path(claim) is True, (
        f"{claim!r} passes the shape guard — that is the point: tightening the "
        "regex is whack-a-mole, asking git what was deleted is not"
    )
