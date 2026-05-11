"""Stub: `atdd babysit` has been decommissioned (coach v9, spec §11.3).

The original implementation lives in ``commands/_archived/babysit.py``
for parity-test reuse. This stub prints the migration message and exits
non-zero so operators are routed to the replacements per spec §0.2.

Absorption map (spec §0.2):
  token-count alerting       → observer rule 06-token-threshold
  bash auto-approval         → observer rule 13-bash-auto-approve
  aggregate approval         → atdd observer aggregate-approve
  naming drift correction    → observer rule 14-canonical-naming-drift
  layout drift correction    → observer rule 15-layout-drift
  violation detection        → observer rules 04-out-of-scope-edit, 16-smoke-skip
  dashboard                  → atdd observer status
  workspace polling          → replaced by event-driven runtime_watcher (no parity test)
  phase-cache-via-labels     → replaced by coach state machine (no parity test)

Backward-compat re-exports
--------------------------
The four symbols below are re-exported so that observer_rules modules
installed at 3.30.0 (which still import from this path) continue to work
after the CLI surface is cut.  They resolve to the archived implementation;
no babysit machinery executes via this module's ``run()``.
"""
from __future__ import annotations

import sys

# Thin compat re-exports — observer_rules ≤3.30 import these from this path.
from atdd.coach.commands._archived.babysit import (  # noqa: F401
    BashPattern,
    _load_bash_patterns,
    classify_prompt,
    correct_layout_drift,
    correct_naming_drift,
    detect_violation,
)

MIGRATION_MESSAGE = (
    "atdd babysit has been removed in coach v9. "
    "Use 'atdd observer status' (dashboard), "
    "'atdd observer aggregate-approve' (batch approve), "
    "or 'atdd coach' (end-to-end) "
    "per atdd-coach-spec-v9.md §0.2."
)


def run(**kwargs) -> int:
    print(MIGRATION_MESSAGE, file=sys.stderr)
    sys.exit(1)
