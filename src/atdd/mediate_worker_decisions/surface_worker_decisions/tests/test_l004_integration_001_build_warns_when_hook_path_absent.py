# URN: test:mediate-worker-decisions:surface-worker-decisions:L004-INTEGRATION-001-build-warns-when-hook-path-absent
# Acceptance: acc:mediate-worker-decisions:L004-INTEGRATION-001-build-warns-when-hook-path-absent
# WMBT: wmbt:mediate-worker-decisions:L004
# Phase: RED
# Layer: integration
# Assertion: behavioral
"""L004-INTEGRATION-001 — resolving while the hook path is absent warns loudly.

When the injected probe reports the wrapper hook path inactive, resolve() still
returns the surfacing values but emits a warning naming the inactive hook path —
so a worker whose decisions would not reach the Feed is never spawned silently.
"""
from __future__ import annotations

import logging

from atdd.mediate_worker_decisions.surface_worker_decisions.src.application.resolve_surfacing_values import (
    resolve,
)
from atdd.mediate_worker_decisions.surface_worker_decisions.tests._helpers import (
    StubProbe,
)


def test_build_warns_when_hook_path_absent(caplog):
    probe = StubProbe(active=False, reason="CMUX_SURFACE_ID not set")

    with caplog.at_level(logging.WARNING):
        values = resolve("claude", probe=probe)

    assert values is not None
    assert any(
        "CMUX_SURFACE_ID" in rec.getMessage() or "hook" in rec.getMessage().lower()
        for rec in caplog.records
    ), "expected a loud warning naming the inactive hook path"
