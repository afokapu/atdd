# URN: test:consolidate-coach-workspace:enforce-surface-conformance:E005-UNIT-002-list-workspaces-emits-only-bare-handles
# Acceptance: acc:consolidate-coach-workspace:E005-UNIT-002-list-workspaces-emits-only-bare-handles
# WMBT: wmbt:consolidate-coach-workspace:E005
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""E005-UNIT-002 — list_workspaces returns only sanitized bare handles.

CmuxBackend.list_workspaces must strip cmux decoration so a downstream
``cmux list-panes --workspace <handle>`` never receives ``*`` / ``[selected]`` /
a workspace title — the exact decoration that crashed `atdd coach 1012` with
``Invalid workspace handle``.
"""
from __future__ import annotations

import re
import types

from atdd.coach.utils import multiplexer as mux

_DECORATED = (
    "* workspace:1  ATDD COACH  [selected]\n"
    "  workspace:5  ATDD358\n"
    "  workspace:6  TOURNAMENT\n"
)
_BARE = re.compile(r"^workspace:\d+$")


def test_list_workspaces_strips_all_decoration(monkeypatch):
    monkeypatch.setattr(
        mux, "_run", lambda *a, **k: types.SimpleNamespace(stdout=_DECORATED)
    )
    handles = mux.CmuxBackend().list_workspaces()

    assert handles == ["workspace:1", "workspace:5", "workspace:6"]
    for h in handles:
        assert _BARE.match(h), h
        assert "*" not in h and "[" not in h and " " not in h
