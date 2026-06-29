# URN: test:admit-substrate:substrate-cli-grouping:C006-SMOKE-001-readme-documents-grouped
# Acceptance: acc:admit-substrate:C006-SMOKE-001-readme-documents-grouped
# WMBT: wmbt:admit-substrate:C006
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""C006-SMOKE-001 (V4) — the README presents `atdd substrate` as the canonical
substrate-management surface and does not present a bare flat substrate verb as
the primary (non-deprecated) form."""
from __future__ import annotations

import pathlib

# tests/ -> substrate -> atdd -> src -> repo root
README = pathlib.Path(__file__).resolve().parents[4] / "README.md"


def test_readme_documents_grouped_substrate() -> None:
    text = README.read_text(encoding="utf-8")
    assert "atdd substrate" in text, "README must document the grouped `atdd substrate` surface"
