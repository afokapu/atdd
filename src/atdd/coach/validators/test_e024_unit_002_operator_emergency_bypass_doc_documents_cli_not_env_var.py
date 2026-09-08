# URN: test:govern-lifecycle:coach-operator-safety-invariants:E066-UNIT-002-operator-emergency-bypass-doc-documents-cli-not-env-var
# Acceptance: acc:govern-lifecycle:E066-UNIT-002-operator-emergency-bypass-doc-documents-cli-not-env-var
# WMBT: wmbt:govern-lifecycle:E066
# Phase: RED
# Layer: backend.unit
# Assertion: structural
"""E024-UNIT-002 — docs/operator-emergency-bypass.md documents CLI, not env-var bypass.

Phase RED: fails — docs/operator-emergency-bypass.md does not exist (pre-#867),
so both content assertions fail: the file neither contains 'atdd emergency'
nor avoids ATDD_SKIP_* tokens (it simply doesn't exist).

Phase GREEN: E024 creates the file with 'atdd emergency' documentation and
explicitly avoids advertising any ATDD_SKIP_* env-var form that agents could
copy-paste.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = [pytest.mark.coach, pytest.mark.platform]

REPO_ROOT = Path(__file__).resolve().parents[4]
_DOC_PATH = REPO_ROOT / "docs" / "operator-emergency-bypass.md"

_REQUIRED_CLI_STRING = "atdd emergency"
_BYPASS_TOKEN_PATTERN = re.compile(r"ATDD_SKIP_[A-Z_]+")


def test_operator_emergency_bypass_doc_documents_cli_not_env_var():
    """E024-UNIT-002: docs doc contains 'atdd emergency' and no ATDD_SKIP_* tokens."""
    if not _DOC_PATH.exists():
        pytest.fail(
            f"docs/operator-emergency-bypass.md not found at {_DOC_PATH}.\n"
            "E024-UNIT-001 is a prerequisite: the file must exist before its "
            "content can be verified."
        )

    text = _DOC_PATH.read_text(encoding="utf-8")

    assert _REQUIRED_CLI_STRING in text, (
        f"docs/operator-emergency-bypass.md does not contain '{_REQUIRED_CLI_STRING}'.\n"
        "E024 requires the doc to document the 'atdd emergency --reason <text>' CLI "
        "as the sole operator override path."
    )

    bypass_matches = _BYPASS_TOKEN_PATTERN.findall(text)
    assert bypass_matches == [], (
        f"docs/operator-emergency-bypass.md contains {len(bypass_matches)} "
        f"ATDD_SKIP_* token(s) — {bypass_matches}.\n"
        "E024 requires the operator doc to avoid advertising env-var bypass tokens "
        "that agents could discover and copy-paste.\n"
        "Fix: replace any ATDD_SKIP_* references with the CLI path 'atdd emergency'."
    )
