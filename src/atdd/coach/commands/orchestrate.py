"""Stub: `atdd orchestrate` has been decommissioned (coach v9, spec §11.3).

The original implementation lives in ``commands/_archived/orchestrate.py``
for parity-test reuse. This stub prints the migration message and exits
non-zero so operators are routed to ``attd coach`` per spec §5.1.
"""
from __future__ import annotations

import sys

MIGRATION_MESSAGE = (
    "atdd orchestrate has been removed in coach v9. "
    "Use 'atdd coach <issue-numbers>' instead. "
    "Migration: every flag maps directly per atdd-coach-spec-v9.md §5.1."
)


def run(**kwargs) -> int:
    print(MIGRATION_MESSAGE, file=sys.stderr)
    sys.exit(1)
