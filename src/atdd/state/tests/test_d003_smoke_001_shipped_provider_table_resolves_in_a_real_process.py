# URN: test:drive-state-machine:record-agent-session-identity:D003-SMOKE-001-shipped-provider-table-resolves-in-a-real-process
# Acceptance: acc:drive-state-machine:D003-SMOKE-001-shipped-provider-table-resolves-in-a-real-process
# WMBT: wmbt:drive-state-machine:D003
# Phase: SMOKE
# Harness: smoke
# Layer: integration
"""D003-SMOKE-001 — the SHIPPED provider table resolves in a real process.

Issue #1540. Guards the failure mode this feature is uniquely prone to: capture
fails CLOSED and SILENTLY. If `agent_session_env.yaml` is not shipped beside the
installed package, nothing errors — `resolve_session` returns None forever, and
every machine simply looks like it has no agents on it.

The unit tests all monkeypatch a fixture table, so none of them would notice.
This one uses the real shipped file, in a separate process that imports the
package the way production does.
"""
from __future__ import annotations

import subprocess
import sys

import pytest

pytestmark = [pytest.mark.platform]

PROBE = """
from atdd.state.agent_session import (
    PROVIDER_TABLE_PATH, load_provider_table, resolve_session,
)

assert PROVIDER_TABLE_PATH.is_file(), f"table not shipped: {PROVIDER_TABLE_PATH}"

rows = load_provider_table()
assert rows, "the shipped provider table resolved to zero rows"
for row in rows:
    assert row.provider and row.session_env, f"incomplete row: {row}"
    assert row.resume_template, f"row cannot render a resume command: {row}"

first = rows[0]
session = resolve_session({first.session_env: "smoke-session-id"})
assert session is not None, f"{first.session_env} did not resolve"
assert session.provider == first.provider
assert session.session_id == "smoke-session-id"

assert resolve_session({}) is None, "an empty environment must resolve to nothing"

print("OK", len(rows))
"""


def test_d003_smoke_001_shipped_provider_table_resolves_in_a_real_process():
    proc = subprocess.run([sys.executable, "-c", PROBE], capture_output=True, text=True)
    assert proc.returncode == 0, (
        f"the shipped provider table did not drive capture:\n{proc.stderr}"
    )
    assert proc.stdout.startswith("OK")
