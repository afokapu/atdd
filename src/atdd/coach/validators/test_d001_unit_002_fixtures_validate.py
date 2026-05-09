# URN: test:freeze-runtime-contracts:runtime-schema-freeze:D001-UNIT-002-fixtures-validate
# Acceptance: acc:freeze-runtime-contracts:D001-UNIT-002-fixtures-validate
# WMBT: wmbt:freeze-runtime-contracts:D001
# Phase: RED
# Layer: backend.integration
# Assertion: behavioral

"""
D001-UNIT-002 — Each schema has at least one valid example fixture
co-located at ``src/atdd/coach/schemas/fixtures/<schema-name>/``;
fixtures collectively cover ``required-only`` and
``required-plus-optional`` shapes.

Phase RED: fails because no fixtures have been committed yet.
Phase GREEN: every fixture round-trips through its schema with zero errors.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pytest

import atdd

ATDD_PKG_DIR = Path(atdd.__file__).resolve().parent
SCHEMAS_DIR = ATDD_PKG_DIR / "coach" / "schemas"
FIXTURES_DIR = SCHEMAS_DIR / "fixtures"

SCHEMA_BASENAMES = (
    "runtime-event",
    "coach-decision",
    "coach-judgment",
    "correction",
    "validator-result",
    "risk-score",
)


def _schema_path(basename: str) -> Path:
    return SCHEMAS_DIR / f"{basename}.schema.json"


def _fixture_dir(basename: str) -> Path:
    return FIXTURES_DIR / basename


def _load_json(path: Path) -> Dict[str, Any]:
    with path.open() as fh:
        return json.load(fh)


def _enumerate_fixtures(basename: str) -> List[Path]:
    d = _fixture_dir(basename)
    if not d.exists():
        return []
    return sorted(p for p in d.glob("*.json") if p.is_file())


@pytest.mark.parametrize("basename", SCHEMA_BASENAMES)
def test_fixture_directory_exists(basename: str) -> None:
    """Every schema has a co-located fixtures directory."""
    d = _fixture_dir(basename)
    assert d.is_dir(), (
        f"Missing fixture directory {d}. Acceptance D001-UNIT-002 "
        f"requires each schema to have at least one example fixture."
    )


@pytest.mark.parametrize("basename", SCHEMA_BASENAMES)
def test_fixture_directory_has_at_least_one_fixture(basename: str) -> None:
    """At least one fixture .json per schema."""
    fixtures = _enumerate_fixtures(basename)
    assert fixtures, (
        f"No fixtures under {_fixture_dir(basename)}. C0 acceptance "
        f"D001-UNIT-002 requires at least one valid example."
    )


def _all_fixture_pairs() -> List[Tuple[str, Path]]:
    pairs: List[Tuple[str, Path]] = []
    for basename in SCHEMA_BASENAMES:
        for f in _enumerate_fixtures(basename):
            pairs.append((basename, f))
    return pairs


@pytest.mark.parametrize(
    "basename,fixture",
    _all_fixture_pairs() or [pytest.param("none", None, marks=pytest.mark.skip(
        reason="no fixtures present yet — covered by directory tests"
    ))],
)
def test_fixture_validates_against_schema(basename: str, fixture: Path) -> None:
    """Every committed fixture validates with zero errors against its schema."""
    jsonschema = pytest.importorskip("jsonschema")
    schema = _load_json(_schema_path(basename))
    instance = _load_json(fixture)
    validator = jsonschema.Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(instance), key=lambda e: e.path)
    assert not errors, (
        f"Fixture {fixture} fails {basename}.schema.json:\n"
        + "\n".join(f"  - {e.message} at /{'/'.join(map(str, e.path))}" for e in errors)
    )


def test_fixtures_collectively_cover_required_only_and_full_shapes() -> None:
    """At least one fixture is required-only; at least one is required-plus-optional.

    "Collectively" is read across the union of all fixtures, not
    per-schema, per the WMBT D001-UNIT-002 ``then`` clause.
    """
    seen_minimal = False
    seen_full = False
    for basename in SCHEMA_BASENAMES:
        schema = _load_json(_schema_path(basename))
        required = set(schema.get("required") or ())
        properties = set((schema.get("properties") or {}).keys())
        optional = properties - required
        for fixture in _enumerate_fixtures(basename):
            instance = _load_json(fixture)
            if not isinstance(instance, dict):
                continue
            keys = set(instance.keys())
            # required-only: exactly the required fields
            if keys == required:
                seen_minimal = True
            # required-plus-optional: contains at least one optional field
            elif required.issubset(keys) and (keys & optional):
                seen_full = True
    assert seen_minimal, (
        "No required-only fixture found across schemas. Add one fixture "
        "(e.g. fixtures/<name>/minimal.json) that omits all optional "
        "fields."
    )
    assert seen_full, (
        "No required-plus-optional fixture found across schemas. Add "
        "one fixture (e.g. fixtures/<name>/full.json) that includes at "
        "least one optional field."
    )
