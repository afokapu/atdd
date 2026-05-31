# URN: test:govern-lifecycle:extract-runtime-agent-control-and-close-spawn-cluster:E039-UNIT-004-cli-return-default-legacy-kill-switch
# Acceptance: acc:govern-lifecycle:E039-UNIT-004-cli-return-default-legacy-kill-switch
# WMBT: wmbt:govern-lifecycle:E039
# Phase: RED
# Assertion: behavioral
# Layer: runtime
"""E039-UNIT-004 — cli-return is the default; ATDD_USE_LEGACY_SPAWN=1 kill switch.

docs/coach-decomposition.md §13.6 ("cli-return is the default control plane") and
§12.4 R-4 (``ATDD_USE_LEGACY_SPAWN=1`` routes back to the pre-extraction path).
"""
from __future__ import annotations

import pytest

pytestmark = [pytest.mark.platform]


def test_default_transport_is_cli_return():
    from atdd.runtime.agent_control import resolve_transport

    assert resolve_transport(env={}) == "cli-return"


def test_legacy_spawn_env_routes_to_tui_scrape():
    from atdd.runtime.agent_control import resolve_transport

    assert resolve_transport(env={"ATDD_USE_LEGACY_SPAWN": "1"}) == "tui-scrape"


def test_legacy_spawn_falsey_values_keep_default():
    from atdd.runtime.agent_control import resolve_transport

    for falsey in ("", "0", "false", "no"):
        assert resolve_transport(env={"ATDD_USE_LEGACY_SPAWN": falsey}) == "cli-return"


def test_spawn_dispatch_uses_cli_return_by_default():
    """The coach spawn dispatch defaults to the cli-return control plane and only
    falls back to the legacy paste path under ATDD_USE_LEGACY_SPAWN=1."""
    from atdd.coach.commands import spawn as spawn_mod

    assert spawn_mod._resolve_transport(env={}) == "cli-return"
    assert spawn_mod._resolve_transport(env={"ATDD_USE_LEGACY_SPAWN": "1"}) == "tui-scrape"
