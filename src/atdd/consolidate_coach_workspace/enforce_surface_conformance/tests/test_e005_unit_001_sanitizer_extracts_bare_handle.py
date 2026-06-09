# URN: test:consolidate-coach-workspace:enforce-surface-conformance:E005-UNIT-001-sanitizer-extracts-bare-handle
# Acceptance: acc:consolidate-coach-workspace:E005-UNIT-001-sanitizer-extracts-bare-handle
# WMBT: wmbt:consolidate-coach-workspace:E005
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""E005-UNIT-001 — the handle sanitizer extracts the bare workspace:N token.

A decorated ``cmux list-workspaces`` line (``* `` marker + title + ``[selected]``)
yields exactly ``workspace:N``; an already-bare handle is returned unchanged.
"""
from __future__ import annotations

from atdd.consolidate_coach_workspace.enforce_surface_conformance.src.domain.workspace_handle import (
    sanitize_workspace_handle,
)


def test_decorated_line_yields_bare_handle():
    assert (
        sanitize_workspace_handle("* workspace:1  ATDD COACH  [selected]")
        == "workspace:1"
    )


def test_already_bare_handle_unchanged():
    assert sanitize_workspace_handle("workspace:5") == "workspace:5"
