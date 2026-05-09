# URN: test:freeze-runtime-contracts:runtime-schema-freeze:D002-UNIT-001-runtime-layout-doc-committed
# Acceptance: acc:freeze-runtime-contracts:D002-UNIT-001-runtime-layout-doc-committed
# WMBT: wmbt:freeze-runtime-contracts:D002
# Phase: RED
# Layer: backend.integration
# Assertion: structural

"""
D002-UNIT-001 — ``src/atdd/coach/schemas/runtime-layout.md`` exists and
documents every file path under ``.atdd/runtime/`` with role / writer /
reader / append-only-vs-rewritten / JSON-line-vs-single-doc, and
references the JSON schemas it complements.

Phase RED: fails because the doc is not yet committed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import atdd

ATDD_PKG_DIR = Path(atdd.__file__).resolve().parent
LAYOUT_DOC = ATDD_PKG_DIR / "coach" / "schemas" / "runtime-layout.md"

# Paths from spec §3.2 / issue body that must each appear in the doc.
REQUIRED_PATHS = (
    ".atdd/runtime/agents/<id>/heartbeat.json",
    ".atdd/runtime/agents/<id>/output.log",
    ".atdd/runtime/agents/<id>/events.jsonl",
    ".atdd/runtime/agents/<id>/corrections.jsonl",
    ".atdd/runtime/coach/decisions.jsonl",
    ".atdd/runtime/coach/judgments.jsonl",
    ".atdd/runtime/validations/<sha>/violations.jsonl",
    ".atdd/runtime/validations/<sha>/risk-score.json",
    ".atdd/runtime/validations/<sha>/suppressed.jsonl",
    ".atdd/runtime/validations/<sha>/stale-suppressions.jsonl",
)

# Top-level directories the WMBT ``then`` clause names explicitly.
REQUIRED_DIRECTORIES = (
    "agents/<id>/",
    "coach/",
    "validations/<sha>/",
    "issue-reviews/<issue-N>/",
    "runs/<run-id>/",
)

# Required per-row metadata columns / labels every documented file must carry.
REQUIRED_METADATA_TOKENS = (
    "role",
    "writer",
    "reader",
    # append-only vs rewritten
    "append-only",
    "rewritten",
    # JSON-line vs single-doc
    "JSON-line",
    "single-doc",
)

# Schemas the doc must reference by relative path.
REFERENCED_SCHEMAS = (
    "runtime-event.schema.json",
    "coach-decision.schema.json",
    "coach-judgment.schema.json",
    "correction.schema.json",
    "validator-result.schema.json",
    "risk-score.schema.json",
)


@pytest.fixture(scope="module")
def doc_text() -> str:
    assert LAYOUT_DOC.exists(), (
        f"Missing {LAYOUT_DOC}. Acceptance D002-UNIT-001 requires "
        f"runtime-layout.md to be committed at "
        f"src/atdd/coach/schemas/runtime-layout.md."
    )
    return LAYOUT_DOC.read_text(encoding="utf-8")


@pytest.mark.parametrize("path", REQUIRED_PATHS)
def test_runtime_layout_documents_path(path: str, doc_text: str) -> None:
    assert path in doc_text, (
        f"runtime-layout.md does not mention {path!r}. Spec §3.2 "
        f"enumerates this file under .atdd/runtime/."
    )


@pytest.mark.parametrize("directory", REQUIRED_DIRECTORIES)
def test_runtime_layout_documents_directory(directory: str, doc_text: str) -> None:
    """``agents/<id>/``, ``coach/``, ``validations/<sha>/``, ``issue-reviews/<issue-N>/``, ``runs/<run-id>/`` appear with child-file contracts."""
    assert directory in doc_text, (
        f"runtime-layout.md does not document the {directory!r} subtree. "
        f"WMBT D002-UNIT-001 requires every top-level subtree to appear "
        f"with its child-file contracts."
    )


@pytest.mark.parametrize("token", REQUIRED_METADATA_TOKENS)
def test_runtime_layout_describes_metadata(token: str, doc_text: str) -> None:
    """Each documented file carries role/writer/reader/appendability/serialization."""
    assert token in doc_text, (
        f"runtime-layout.md does not describe {token!r}. WMBT "
        f"D002-UNIT-001 requires every file's role, writer, reader, "
        f"append-only-vs-rewritten, and JSON-line-vs-single-doc to be "
        f"documented."
    )


@pytest.mark.parametrize("schema", REFERENCED_SCHEMAS)
def test_runtime_layout_references_schemas(schema: str, doc_text: str) -> None:
    """The doc references the JSON schemas it complements by relative path."""
    assert schema in doc_text, (
        f"runtime-layout.md does not reference {schema!r}. WMBT "
        f"D002-UNIT-001 requires schema cross-references so consumers "
        f"can find the shape contract for each documented file."
    )
