# URN: test:govern-lifecycle:coach-operator-safety-invariants:E066-UNIT-001-operator-emergency-bypass-doc-exists
# Acceptance: acc:govern-lifecycle:E066-UNIT-001-operator-emergency-bypass-doc-exists
# WMBT: wmbt:govern-lifecycle:E066
# Phase: RED
# Layer: backend.unit
# Assertion: structural
"""E024-UNIT-001 — docs/operator-emergency-bypass.md must exist in the repository.

Phase RED: fails — docs/operator-emergency-bypass.md does not exist (pre-#867).
The operator emergency override path is undocumented; the only existing
documentation is the retired ATDD_SKIP_* inline references in CLAUDE.md.

Phase GREEN: E024 creates docs/operator-emergency-bypass.md documenting the
'atdd emergency --reason' CLI as the sole emergency override path.
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = [pytest.mark.coach, pytest.mark.platform]

REPO_ROOT = Path(__file__).resolve().parents[4]
_DOC_PATH = REPO_ROOT / "docs" / "operator-emergency-bypass.md"


def test_operator_emergency_bypass_doc_exists():
    """E024-UNIT-001: Path('docs/operator-emergency-bypass.md').exists() returns True."""
    assert _DOC_PATH.exists(), (
        f"docs/operator-emergency-bypass.md not found at {_DOC_PATH}.\n"
        "E024 requires this operator-only doc to exist so agents redirected from "
        "CLAUDE.md have a valid destination.\n"
        "Fix: create docs/operator-emergency-bypass.md documenting the "
        "'atdd emergency --reason <text>' CLI path (5-minute TTL .atdd/EMERGENCY_BYPASS)."
    )
