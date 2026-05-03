"""
Unit tests for atdd.coach.utils.rule_id_registry.

URN: urn:atdd:test:coach:utils:rule_id_registry
Issue: #387 — Registry Coherence Validator (Phase 1: walker)

The walker reads every ``src/atdd/**/conventions/*.yaml`` and normalizes the
three observed ``rules:`` shapes into a single ``{rule_id: RuleMetadata}``
index. Shape A and B contribute IDs; shape C is skipped.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from atdd.coach.utils.rule_id_registry import (
    RuleMetadata,
    build_registry,
)


pytestmark = [pytest.mark.coach, pytest.mark.platform]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
def _write(p: Path, body: str) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body)
    return p


@pytest.fixture
def shape_a_file(tmp_path: Path) -> Path:
    """Shape A: rules: is a list of objects, each with `id:`."""
    return _write(
        tmp_path / "conventions" / "alpha.convention.yaml",
        """
schema_version: "1.0.0"
convention_id: "test.alpha"
rules:
  - id: "GREEN-URN-001"
    severity: 3
    description: "Component URN required as first non-empty line"
    introduced_in: "1.50.0"
  - id: "GREEN-URN-002"
    severity: 3
    description: "URN must include layer segment"
    recipe: "adapter"
""",
    )


@pytest.fixture
def shape_b_file(tmp_path: Path) -> Path:
    """Shape B: rules: is a mapping keyed by rule id."""
    return _write(
        tmp_path / "conventions" / "bravo.convention.yaml",
        """
schema_version: "1.0.0"
convention_id: "test.bravo"
rules:
  COACH-SILENT-SWALLOW-001:
    id: COACH-SILENT-SWALLOW-001
    severity: 4
    description: "Exception handlers must log, re-raise, or otherwise observably react"
""",
    )


@pytest.fixture
def shape_c_file(tmp_path: Path) -> Path:
    """Shape C: rules: is a semantic-keyed mapping with no `id:` field."""
    return _write(
        tmp_path / "conventions" / "charlie.convention.yaml",
        """
schema_version: "1.0.0"
convention_id: "test.charlie"
rules:
  worktree_per_issue:
    rule: "Every orchestrated issue MUST have its own git worktree"
    anti_pattern: "Reusing a worktree across issues"
    enforced_by: "atdd orchestrate"
""",
    )


@pytest.fixture
def mixed_shape_file(tmp_path: Path) -> Path:
    """Shape A nested under a key, plus shape B at top-level."""
    return _write(
        tmp_path / "conventions" / "delta.convention.yaml",
        """
schema_version: "1.0.0"
convention_id: "test.delta"
rules:
  COACH-MIX-001:
    id: COACH-MIX-001
    severity: 2
    description: "top-level shape-B rule"
green_phase:
  urn_naming:
    rules:
      - id: "GREEN-MIX-002"
        severity: 3
        description: "nested shape-A rule"
""",
    )


@pytest.fixture
def malformed_yaml_file(tmp_path: Path) -> Path:
    return _write(
        tmp_path / "conventions" / "broken.convention.yaml",
        "rules:\n  - id: BAD\n    description: missing severity\n  -- not yaml --\n",
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
class TestBuildRegistryShapes:
    def test_shape_a_contributes_rules(self, shape_a_file: Path):
        registry = build_registry(roots=[shape_a_file.parent.parent])
        assert "GREEN-URN-001" in registry
        assert "GREEN-URN-002" in registry

    def test_shape_a_metadata_normalized(self, shape_a_file: Path):
        registry = build_registry(roots=[shape_a_file.parent.parent])
        meta = registry["GREEN-URN-001"]
        assert isinstance(meta, RuleMetadata)
        assert meta.severity == 3
        assert "URN required" in meta.description
        assert meta.introduced_in == "1.50.0"
        assert meta.convention_path == shape_a_file
        # recipe is optional
        assert registry["GREEN-URN-002"].recipe == "adapter"

    def test_shape_b_contributes_rules(self, shape_b_file: Path):
        registry = build_registry(roots=[shape_b_file.parent.parent])
        assert "COACH-SILENT-SWALLOW-001" in registry
        assert registry["COACH-SILENT-SWALLOW-001"].severity == 4

    def test_shape_c_skipped(self, shape_c_file: Path):
        """Shape C entries have no id: field; they must NOT pollute the registry."""
        registry = build_registry(roots=[shape_c_file.parent.parent])
        assert "worktree_per_issue" not in registry
        assert registry == {}

    def test_mixed_shape_file_merges_both(self, mixed_shape_file: Path):
        registry = build_registry(roots=[mixed_shape_file.parent.parent])
        assert "COACH-MIX-001" in registry
        assert "GREEN-MIX-002" in registry


class TestBuildRegistryWalking:
    def test_walks_every_convention_file(
        self, shape_a_file: Path, shape_b_file: Path, shape_c_file: Path,
    ):
        # All three live under the same conventions/ dir.
        root = shape_a_file.parent.parent
        registry = build_registry(roots=[root])
        # Shape A + B contribute, shape C is skipped.
        assert {"GREEN-URN-001", "GREEN-URN-002", "COACH-SILENT-SWALLOW-001"} <= set(registry)

    def test_malformed_yaml_does_not_raise(self, malformed_yaml_file: Path):
        # Malformed YAML must not blow up the walker — surface the path
        # silently (or via debug log), but return a usable registry.
        registry = build_registry(roots=[malformed_yaml_file.parent.parent])
        assert isinstance(registry, dict)


class TestBuildRegistryAgainstRealConventions:
    """Smoke test against the real toolkit conventions tree."""

    def test_real_registry_contains_known_ids(self):
        registry = build_registry()
        # Substrate IDs declared in the toolkit:
        # green.convention.yaml ships GREEN-URN-001 (shape A)
        # logging.convention.yaml ships COACH-SILENT-SWALLOW-001 (shape A)
        assert "COACH-SILENT-SWALLOW-001" in registry, (
            f"expected COACH-SILENT-SWALLOW-001 in real registry; "
            f"got {sorted(registry)[:5]}..."
        )

    def test_real_registry_metadata_is_RuleMetadata(self):
        registry = build_registry()
        for rule_id, meta in registry.items():
            assert isinstance(meta, RuleMetadata), f"{rule_id}: {type(meta)}"
            assert isinstance(meta.convention_path, Path)
            assert isinstance(meta.description, str)
