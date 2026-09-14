# URN: test:migrate-projection-authority:decommission-manifest-fallback:Y002-UNIT-004-shadow-offers-no-manifest-source
# Acceptance: acc:migrate-projection-authority:Y002-UNIT-004-shadow-offers-no-manifest-source
# WMBT: wmbt:migrate-projection-authority:Y002
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: The drift report offers no comparison source that resolves .atdd/manifest.yaml, so `atdd state shadow` — a shipped command reached on every push — holds no manifest read path. Refs #2023.
"""Shadow offers no manifest source (Y002-UNIT-004).

wagon: migrate-projection-authority | feature: decommission-manifest-fallback | phase: RED
WMBT: wmbt:migrate-projection-authority:Y002

``atdd state shadow`` is documented as "the drift report against the committed projection AND the
manifest-derived one". The manifest-derived one cannot be produced: ``_manifest_documents`` calls
``read_manifest(manifest_path(root))`` against a file CORE-034 deleted, and returns
``(None, why-not)`` every time. The source is therefore a *permanently* skipped comparison, reported
as a skip rather than a failure — which is correct for a transient absence and misleading for a
structural one.

Two things follow, and this acceptance pins both. The report must not advertise a comparison it
cannot perform; and a shipped verb must not retain a helper that resolves the manifest path, which
is the read path Y002 exists to remove. Refs #2023 / #1400.
"""
from __future__ import annotations

from atdd.state import shadow


def test_y002_unit_004_sources_names_only_producible_sources() -> None:
    """SOURCES names exactly what a shadow run can actually compare against."""
    assert shadow.SOURCES == (shadow.SOURCE_COMMITTED,), (
        f"SOURCES={shadow.SOURCES!r} still advertises a manifest-derived projection; "
        "CORE-034 deleted its input, so that comparison reports a skip on every run and "
        "'shadow is clean' means less than the operator is told it means"
    )


def test_y002_unit_004_no_manifest_source_constant_remains() -> None:
    """The constant is the advertisement; removing the helper without it leaves the claim."""
    assert not hasattr(shadow, "SOURCE_MANIFEST"), (
        "shadow.SOURCE_MANIFEST still exists, so the report can still name a source it cannot build"
    )


def test_y002_unit_004_no_helper_resolves_the_manifest_path() -> None:
    """No helper remains that opens the manifest on the report's behalf."""
    assert not hasattr(shadow, "_manifest_documents"), (
        "shadow._manifest_documents still resolves manifest_path(root); it is a manifest read path "
        "reachable from a verb that runs on every push and pull request"
    )
