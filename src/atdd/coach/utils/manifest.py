"""
Manifest file detection utilities.

Helpers for distinguishing wagon-level manifest/aggregator files from real
feature definitions inside ``plan/<wagon>/features/``.

Background
----------
The ATDD convention (see ``coach/templates/ATDD.md``) declares the wagon
feature manifest at ``plan/*/_features.yaml``. The shared ``feature_files``
fixture (``coach/validators/shared_fixtures.py``) globs ``*.yaml`` inside
each ``features/`` directory and yields every match — including
``_features.yaml``. Coverage validators must skip the manifest entry,
otherwise the underscore-to-hyphen slug normalisation produces an
illegal slug ``-features`` that can never appear in any wagon
manifest's ``features[]`` list (it would fail the URN regex
``^feature:[a-z][a-z0-9-]+:[a-z][a-z0-9-]+$``).

Prior to consolidation, the planner and coder validators each carried
their own copy of this skip helper, and at least one call site (the
planner) lacked the helper entirely — see issue #252. This module is
the single source of truth so all sister validators stay in sync.
"""

# Slugs produced by stem extraction + underscore→hyphen normalisation when
# the file is a manifest/aggregator rather than a real feature definition.
# - "_features"  → raw stem of "_features.yaml"
# - "-features"  → after replace("_", "-")
# - ""           → defensive: stem of an empty/odd filename
_MANIFEST_SLUGS = frozenset(("-features", "_features", ""))


def is_manifest_slug(feature_slug: str) -> bool:
    """
    Return True if ``feature_slug`` refers to a manifest file, not a feature.

    Manifest files like ``_features.yaml`` produce slugs such as
    ``-features`` or ``_features`` after stem extraction and hyphen
    normalisation. Coverage validators iterating ``feature_files`` should
    skip these entries before applying any slug- or URN-based checks.
    """
    return feature_slug in _MANIFEST_SLUGS
