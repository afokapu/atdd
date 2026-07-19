# URN: test:train:issue-lifecycle:record-agent-session-identity:E2E-002-shipped-table-smoke
# Train: train:issue-lifecycle:record-agent-session-identity
# Phase: SMOKE
# Layer: assembly
# Runtime: python
# Smoke: true
# Assertion: behavioral
# Purpose: SMOKE — the SHIPPED provider table loads from the installed package
#          and drives capture, so a packaging miss (the table not shipped in the
#          wheel) is caught here rather than by silence in production.
"""Smoke test for train:issue-lifecycle:record-agent-session-identity.

Guards the failure mode this feature is uniquely prone to: capture fails CLOSED
and SILENTLY. If `agent_session_env.yaml` is missing from the wheel, nothing
errors — `resolve_session` simply returns None forever, and every machine looks
like it has no agents on it.

So this asserts the shipped table is present, parses, and actually resolves a
session, in a subprocess importing the package the way production does.
"""
from __future__ import annotations

import subprocess
import sys

import pytest

pytestmark = [pytest.mark.platform]

PROBE = """
import sys
from atdd.state.agent_session import (
    PROVIDER_TABLE_PATH, load_provider_table, resolve_session,
)

assert PROVIDER_TABLE_PATH.is_file(), f"table not shipped: {PROVIDER_TABLE_PATH}"

rows = load_provider_table()
assert rows, "the shipped provider table resolved to zero rows"

for row in rows:
    assert row.provider and row.session_env, f"incomplete row: {row}"
    assert row.resume_template, f"row cannot render a resume command: {row}"

# a session resolves from the first row's own env var
first = rows[0]
session = resolve_session({first.session_env: "smoke-session-id"})
assert session is not None, f"{first.session_env} did not resolve"
assert session.provider == first.provider
assert session.session_id == "smoke-session-id"

# and an empty environment resolves to nothing, without raising
assert resolve_session({}) is None

print("OK", len(rows))
"""


def test_shipped_provider_table_loads_and_resolves():
    proc = subprocess.run(
        [sys.executable, "-c", PROBE], capture_output=True, text=True,
    )
    assert proc.returncode == 0, (
        f"the shipped provider table did not drive capture:\n{proc.stderr}"
    )
    assert proc.stdout.startswith("OK")
