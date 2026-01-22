"""
SPEC-COACH-UTILS-0290: Add features section and simplify WMBT counts in wagon registry

Tests enrichment of _wagons.yaml with features list and simplified WMBT totals.
"""
import pytest
import yaml
from pathlib import Path
from tempfile import TemporaryDirectory


def test_add_features_and_simplify_wmbt(tmp_path):
    """
    SPEC-COACH-UTILS-0290: Add features section and simplify WMBT counts in wagon registry

    Given: _wagons.yaml exists with wagon entries
           Each wagon entry may have full wmbt details or empty wmbt: {}
           Individual wagon manifests contain features: array with URN objects
           Individual wagon manifests contain wmbt.total count
    When: Enriching _wagons.yaml with features and WMBT counts
    Then: Each wagon entry in _wagons.yaml has a features: section
          features: section contains array of feature URNs from wagon manifest
          Wagons without features in manifest get empty features: []
          wmbt: {} or wmbt detailed entries are replaced with total: N
          total value comes from wagon manifest wmbt.total field
          All other wagon fields remain unchanged
          YAML structure and formatting preserved
    """
    # Setup test directories
    plan_dir = tmp_path / "plan"
    plan_dir.mkdir()

    # Create sample wagon manifests with features and wmbt.total
    wagon_a_dir = plan_dir / "wagon_a"
    wagon_a_dir.mkdir()
    wagon_a_manifest = wagon_a_dir / "_wagon_a.yaml"
    wagon_a_data = {
        "wagon": "wagon-a",
        "description": "Test wagon A",
        "theme": "commons",
        "subject": "system:test",
        "context": "test",
        "action": "test action",
        "goal": "test goal",
        "outcome": "test outcome",
        "produce": [{"name": "test:artifact", "contract": None, "telemetry": None}],
        "consume": [],
        "features": [
            {"urn": "feature:wagon-a.feature-one"},
            {"urn": "feature:wagon-a.feature-two"}
        ],
        "wmbt": {
            "L001": "Test WMBT 1",
            "P001": "Test WMBT 2",
            "total": 2
        }
    }
    with open(wagon_a_manifest, 'w') as f:
        yaml.dump(wagon_a_data, f, default_flow_style=False, sort_keys=False)

    # Create wagon B with no features
    wagon_b_dir = plan_dir / "wagon_b"
    wagon_b_dir.mkdir()
    wagon_b_manifest = wagon_b_dir / "_wagon_b.yaml"
    wagon_b_data = {
        "wagon": "wagon-b",
        "description": "Test wagon B",
        "theme": "commons",
        "subject": "system:test",
        "context": "test",
        "action": "test action",
        "goal": "test goal",
        "outcome": "test outcome",
        "produce": [{"name": "test:artifact", "contract": None, "telemetry": None}],
        "consume": [],
        "wmbt": {
            "total": 0
        }
    }
    with open(wagon_b_manifest, 'w') as f:
        yaml.dump(wagon_b_data, f, default_flow_style=False, sort_keys=False)

    # Create _wagons.yaml with wagons that need enrichment
    wagons_file = plan_dir / "_wagons.yaml"
    wagons_data = {
        "wagons": [
            {
                "wagon": "wagon-a",
                "description": "Test wagon A",
                "theme": "commons",
                "subject": "system:test",
                "context": "test",
                "action": "test action",
                "goal": "test goal",
                "outcome": "test outcome",
                "produce": [{"name": "test:artifact", "to": "external"}],
                "consume": [],
                "wmbt": {
                    "L001": "Test WMBT 1",
                    "P001": "Test WMBT 2"
                },
                "total": 2,
                "manifest": "plan/wagon_a/_wagon_a.yaml",
                "path": "plan/wagon_a/"
            },
            {
                "wagon": "wagon-b",
                "description": "Test wagon B",
                "theme": "commons",
                "subject": "system:test",
                "context": "test",
                "action": "test action",
                "goal": "test goal",
                "outcome": "test outcome",
                "produce": [{"name": "test:artifact", "to": "external"}],
                "consume": [],
                "wmbt": {},
                "total": 0,
                "manifest": "plan/wagon_b/_wagon_b.yaml",
                "path": "plan/wagon_b/"
            }
        ]
    }
    with open(wagons_file, 'w') as f:
        yaml.dump(wagons_data, f, default_flow_style=False, sort_keys=False)

    # Import and call the enrichment via RegistryBuilder
    from atdd.coach.commands.registry import RegistryBuilder

    # Create builder and enrich registry
    builder = RegistryBuilder(tmp_path)
    builder.enrich_wagon_registry()

    # Load the enriched _wagons.yaml
    with open(wagons_file, 'r') as f:
        enriched_data = yaml.safe_load(f)

    # Assertions
    wagons = enriched_data["wagons"]

    # Check wagon-a
    wagon_a = next(w for w in wagons if w["wagon"] == "wagon-a")
    assert "features" in wagon_a, "wagon-a should have features section"
    assert wagon_a["features"] == [
        {"urn": "feature:wagon-a.feature-one"},
        {"urn": "feature:wagon-a.feature-two"}
    ], "wagon-a features should match manifest"
    assert "wmbt" in wagon_a, "wagon-a should have wmbt object"
    assert wagon_a["wmbt"]["total"] == 2, "wagon-a wmbt.total should be 2"
    assert wagon_a["wmbt"]["coverage"] == 0, "wagon-a wmbt.coverage should be 0"
    assert "L001" not in wagon_a["wmbt"], "wagon-a wmbt should not have detailed entries"
    assert "total" not in wagon_a or wagon_a.get("total") is None, "wagon-a should not have root-level total field"

    # Check wagon-b
    wagon_b = next(w for w in wagons if w["wagon"] == "wagon-b")
    assert "features" in wagon_b, "wagon-b should have features section"
    assert wagon_b["features"] == [], "wagon-b should have empty features list"
    assert "wmbt" in wagon_b, "wagon-b should have wmbt object"
    assert wagon_b["wmbt"]["total"] == 0, "wagon-b wmbt.total should be 0"
    assert wagon_b["wmbt"]["coverage"] == 0, "wagon-b wmbt.coverage should be 0"
    assert "total" not in wagon_b or wagon_b.get("total") is None, "wagon-b should not have root-level total field"

    # Check other fields remain unchanged
    assert wagon_a["description"] == "Test wagon A"
    assert wagon_a["manifest"] == "plan/wagon_a/_wagon_a.yaml"
    assert wagon_b["description"] == "Test wagon B"
    assert wagon_b["manifest"] == "plan/wagon_b/_wagon_b.yaml"
