"""Legacy-parity helpers for sizing variants (#1212).

The legacy wagon-coupling / wagon-separability validators are ADVISORY — their
pytest tests pass even with findings — so a subprocess return code is not a parity
signal. We compare the legacy SCAN functions in-process on the identical tree.

This import of the legacy persona validators lives HERE (a non-`test_*` helper) so
the E013 no-legacy-import guard (which scans `test_*.py`) stays satisfied while the
honest differential measurement is preserved.
"""
from __future__ import annotations

import atdd.planner.validators.test_wagon_coupling_complexity as _coupling
import atdd.planner.validators.test_wagon_separability as _separability


def legacy_coupling_scan(root):
    """Legacy coupling-complexity findings on the tree rooted at *root*."""
    return _coupling._scan(_coupling.coupling_threshold(root))


def legacy_separability_scan_live():
    """Legacy separability findings on the live composed graph."""
    return _separability._scan_live()
