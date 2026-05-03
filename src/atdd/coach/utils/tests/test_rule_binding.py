# URN: urn:atdd:test:coach:utils:rule_binding
# WMBT: wmbt:govern-lifecycle:rule-id-runtime-binding
# Issue: #388

"""Unit tests for ``atdd.coach.utils.rule_binding``.

The helper loads rule metadata from convention files at module-import time so
validators can stop redeclaring ``RULE_ID`` / ``RULE_SEVERITY`` constants.

Acceptance shape (mirrors issue #388 § Phase 1):

* ``bind_rule(rule_id) -> RuleMetadata`` returns severity, description,
  recipe, introduced_in, source_path drawn from the convention.
* ``RuleMetadata.fix_hint_ref`` is ``"recipe:{recipe}"`` if ``recipe`` is set,
  else ``None`` — matches the structured-pointer format in
  ``src/atdd/coach/validators/_violation.py``.
* ``RuleNotInRegistryError`` raised when the rule_id is unregistered.
* ``AmbiguousRuleError`` raised when the rule_id is declared in two
  convention files; message lists both ``source_path`` values.
* ``clear_cache()`` drops the module-level registry cache; supports
  ``override_roots=[...]`` for tests to point at fixture conventions.
"""

from __future__ import annotations

from pathlib import Path

import pytest


pytestmark = [pytest.mark.platform]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _reset_cache():
    """Reset the binding cache between every test case."""
    from atdd.coach.utils.rule_binding import clear_cache

    clear_cache()
    yield
    clear_cache()


@pytest.fixture
def fixture_root(tmp_path: Path) -> Path:
    """Create a writable convention root that tests can populate."""
    root = tmp_path / "atdd"
    root.mkdir()
    return root


def _write_convention(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Successful binding against the live conventions
# ---------------------------------------------------------------------------
def test_bind_rule_returns_metadata_for_known_rule():
    """Binding a real published rule yields metadata pulled from the convention."""
    from atdd.coach.utils.rule_binding import bind_rule, RuleMetadata

    meta = bind_rule("COACH-SILENT-SWALLOW-001")

    assert isinstance(meta, RuleMetadata)
    assert meta.rule_id == "COACH-SILENT-SWALLOW-001"
    assert meta.severity == 4
    assert isinstance(meta.description, str) and meta.description
    assert meta.source_path is not None
    assert str(meta.source_path).endswith("logging.convention.yaml")


def test_bind_rule_metadata_is_frozen():
    """RuleMetadata is a frozen dataclass — no accidental mutation."""
    from dataclasses import FrozenInstanceError

    from atdd.coach.utils.rule_binding import bind_rule

    meta = bind_rule("COACH-SILENT-SWALLOW-001")
    with pytest.raises(FrozenInstanceError):
        meta.severity = 99  # type: ignore[misc]


def test_bind_rule_severity_matches_convention():
    """Severity returned by bind_rule equals the convention's declared value."""
    import yaml

    import atdd
    from atdd.coach.utils.rule_binding import bind_rule

    convention = (
        Path(atdd.__file__).resolve().parent
        / "coder"
        / "conventions"
        / "logging.convention.yaml"
    )
    data = yaml.safe_load(convention.read_text(encoding="utf-8"))
    declared = next(
        r for r in data["rules"] if r["id"] == "COACH-SILENT-SWALLOW-001"
    )

    meta = bind_rule("COACH-SILENT-SWALLOW-001")
    assert meta.severity == declared["severity"]
    assert meta.description == declared["description"]


# ---------------------------------------------------------------------------
# fix_hint_ref derivation
# ---------------------------------------------------------------------------
def test_fix_hint_ref_none_when_recipe_absent():
    """Pilot rule has no ``recipe:`` — derived ``fix_hint_ref`` is ``None``."""
    from atdd.coach.utils.rule_binding import bind_rule

    meta = bind_rule("COACH-SILENT-SWALLOW-001")
    assert meta.recipe is None
    assert meta.fix_hint_ref is None


def test_fix_hint_ref_when_recipe_set(fixture_root: Path):
    """``recipe: adapter`` in convention → ``fix_hint_ref == "recipe:adapter"``."""
    from atdd.coach.utils.rule_binding import bind_rule, clear_cache

    _write_convention(
        fixture_root / "fake.convention.yaml",
        """
schema_version: "1.0.0"
rules:
  - id: COACH-FIXTURE-001
    severity: 3
    description: "Fixture rule for fix_hint_ref derivation"
    recipe: adapter
    introduced_in: "1.65.0"
""".lstrip(),
    )

    clear_cache(override_roots=[fixture_root])
    meta = bind_rule("COACH-FIXTURE-001")

    assert meta.recipe == "adapter"
    assert meta.fix_hint_ref == "recipe:adapter"


def test_introduced_in_field_loaded(fixture_root: Path):
    """``introduced_in`` is preserved verbatim on RuleMetadata."""
    from atdd.coach.utils.rule_binding import bind_rule, clear_cache

    _write_convention(
        fixture_root / "fake.convention.yaml",
        """
schema_version: "1.0.0"
rules:
  - id: COACH-FIXTURE-002
    severity: 1
    description: "Fixture for introduced_in"
    introduced_in: "1.42.0"
""".lstrip(),
    )

    clear_cache(override_roots=[fixture_root])
    meta = bind_rule("COACH-FIXTURE-002")
    assert meta.introduced_in == "1.42.0"


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------
def test_bind_unknown_rule_raises_not_in_registry():
    """Binding an unregistered rule_id raises ``RuleNotInRegistryError``."""
    from atdd.coach.utils.rule_binding import (
        bind_rule,
        RuleNotInRegistryError,
    )

    with pytest.raises(RuleNotInRegistryError) as exc:
        bind_rule("COACH-NONEXISTENT-999")

    msg = str(exc.value)
    assert "COACH-NONEXISTENT-999" in msg


def test_bind_duplicate_rule_raises_ambiguous(fixture_root: Path):
    """Same rule_id in two conventions → ``AmbiguousRuleError`` lists both paths."""
    from atdd.coach.utils.rule_binding import (
        AmbiguousRuleError,
        bind_rule,
        clear_cache,
    )

    body = """
schema_version: "1.0.0"
rules:
  - id: COACH-DUP-001
    severity: 2
    description: "Duplicate rule for ambiguity test"
""".lstrip()

    a = _write_convention(fixture_root / "a" / "a.convention.yaml", body)
    b = _write_convention(fixture_root / "b" / "b.convention.yaml", body)

    clear_cache(override_roots=[fixture_root])

    with pytest.raises(AmbiguousRuleError) as exc:
        bind_rule("COACH-DUP-001")

    msg = str(exc.value)
    assert "COACH-DUP-001" in msg
    assert str(a) in msg
    assert str(b) in msg


# ---------------------------------------------------------------------------
# Cache behavior
# ---------------------------------------------------------------------------
def test_clear_cache_drops_registry(fixture_root: Path):
    """``clear_cache()`` forces the next bind_rule call to re-walk conventions."""
    from atdd.coach.utils.rule_binding import (
        RuleNotInRegistryError,
        bind_rule,
        clear_cache,
    )

    convention_path = fixture_root / "fake.convention.yaml"
    _write_convention(
        convention_path,
        """
schema_version: "1.0.0"
rules:
  - id: COACH-CACHE-001
    severity: 1
    description: "Cache eviction probe"
""".lstrip(),
    )

    clear_cache(override_roots=[fixture_root])
    meta = bind_rule("COACH-CACHE-001")
    assert meta.severity == 1

    # Re-write the convention with severity 5 — without clear_cache the bound
    # value should remain stale (proves the cache exists).
    _write_convention(
        convention_path,
        """
schema_version: "1.0.0"
rules:
  - id: COACH-CACHE-001
    severity: 5
    description: "Cache eviction probe"
""".lstrip(),
    )
    cached = bind_rule("COACH-CACHE-001")
    assert cached.severity == 1, "expected cached value before clear_cache()"

    clear_cache(override_roots=[fixture_root])
    fresh = bind_rule("COACH-CACHE-001")
    assert fresh.severity == 5

    # Confirm clear_cache() with no override resets to the live conventions —
    # the fixture rule is no longer reachable.
    clear_cache()
    with pytest.raises(RuleNotInRegistryError):
        bind_rule("COACH-CACHE-001")


# ---------------------------------------------------------------------------
# Walker centralization (Phase 1 deliverable)
# ---------------------------------------------------------------------------
def test_walker_exports_extract_rules():
    """``extract_rules`` and ``_walk_rules`` are exposed for shared consumption."""
    from atdd.coach.utils import rule_binding

    assert callable(getattr(rule_binding, "extract_rules", None))
    assert callable(getattr(rule_binding, "_walk_rules", None))


def test_extract_rules_returns_structured_rules(fixture_root: Path):
    """extract_rules yields (file, yaml_path, rule_dict) for every dict rule."""
    from atdd.coach.utils.rule_binding import extract_rules

    path = _write_convention(
        fixture_root / "extract.convention.yaml",
        """
schema_version: "1.0.0"
section:
  rules:
    - id: COACH-EXT-001
      severity: 1
      description: "extract_rules probe"
""".lstrip(),
    )

    rules = extract_rules(path)
    assert len(rules) == 1
    file_path, yaml_path, rule = rules[0]
    assert file_path == path
    assert rule["id"] == "COACH-EXT-001"
    assert "section" in yaml_path
