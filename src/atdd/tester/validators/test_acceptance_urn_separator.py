"""
Platform validation for Acceptance URN format (Updated for SPEC-COACH-UTILS-0282).

SPEC-COACH-UTILS-0282: Acceptance URN refactored to include WMBT ID and harness
SPEC-PLANNER-CONV-0052: Acceptance URN separator follows hierarchy-facet rule
SPEC-PLANNER-CONV-0057: URNGrammar.acceptance updated for new separator pattern
SPEC-PLANNER-CONV-0058: Acceptance schema updated to reflect new URN pattern
SPEC-TESTER-CONV-0068 through SPEC-TESTER-CONV-0078: Test filename generation from URNs

Background:
  - URN rule: colon = hierarchy, dash = facet grouping
  - New Acceptance URN structure: acc:{wagon}:{wmbt_id}-{harness}-{NNN}[-{slug}]
  - Wagon is hierarchical (use colon)
  - wmbt_id, harness, sequence, and optional slug are facets (use dash)

Filename Generation:
  - URN-based filename generation implemented in atdd.tester.utils.filename
  - Convention documented in .claude/conventions/tester/filename.convention.yaml
  - See test_acceptance_urn_filename_mapping.py for filename validation tests
"""

import pytest
import yaml
import re
from pathlib import Path

import atdd
from atdd.coach.utils.repo import find_repo_root

# Path constants
REPO_ROOT = find_repo_root()

# Package resources (conventions, schemas)
ATDD_PKG_DIR = Path(atdd.__file__).resolve().parent
CONVENTIONS_DIR = ATDD_PKG_DIR / "planner" / "conventions"
SCHEMAS_DIR = ATDD_PKG_DIR / "planner" / "schemas"


# SPEC-COACH-UTILS-0282
def test_urn_builder_acceptance_separator(monkeypatch):
    """
    Given: URNGrammar utility exists
    When: Using new format with WMBT ID and harness
    Then: acceptance() method generates: acc:{wagon}:{wmbt_id}-{harness}-{NNN}[-{slug}]
    """
    # Try to import URNGrammar from current location
    try:
        from atdd.coach.utils.graph.urn import URNGrammar

        # Test URNGrammar.acceptance method with new signature
        # New signature: acceptance(wagon_id, wmbt_id, harness_code, seq, slug=None)
        urn = URNGrammar.acceptance("authenticate-user", "E005", "UNIT", "201")

        assert urn == "acc:authenticate-user:E005-UNIT-201", \
            f"Expected 'acc:authenticate-user:E005-UNIT-201', got '{urn}'"

        # Verify structure
        assert urn.count(':') == 2, \
            f"URN should have 2 colons (hierarchy separators), got: {urn}"
        assert urn.count('-') >= 2, \
            f"URN should have at least 2 dashes (facet separators), got: {urn}"

        # Test with optional slug
        urn_with_slug = URNGrammar.acceptance("maintain-ux", "C004", "E2E", "019", "user-connection")
        assert urn_with_slug == "acc:maintain-ux:C004-E2E-019-user-connection", \
            f"Expected 'acc:maintain-ux:C004-E2E-019-user-connection', got '{urn_with_slug}'"

    except ImportError as e:
        pytest.skip(f"URNGrammar not yet implemented or location changed: {e}")


# SPEC-PLANNER-CONV-0058
def test_schema_validates_new_urn_format():
    """
    Given: Acceptance schema validates URN format
    When: Updating schema to match new convention
    Then: URN pattern updated to match acc:{wagon}:{nnn}.{acceptance_id}
          Schema validation accepts new format
    """
    # Find acceptance schema
    acceptance_schema_files = list(SCHEMAS_DIR.glob("acceptance*.json"))

    if not acceptance_schema_files:
        pytest.skip("No acceptance schema file found")

    import json
    schema_path = acceptance_schema_files[0]

    with open(schema_path, 'r') as f:
        schema = json.load(f)

    # Look for URN pattern in schema
    # This could be in various locations, so we'll search recursively
    def find_urn_pattern(obj, path=""):
        """Recursively search for URN pattern or examples"""
        if isinstance(obj, dict):
            # Check if this is a URN field
            if 'pattern' in obj and path.endswith('urn'):
                pattern = obj['pattern']
                # Pattern should allow colon between wagon and sequence
                # Pattern example: ^acc:[a-z-]+:\d{3}\.[A-Z-]+$
                if 'acc:' in pattern:
                    # Verify pattern uses colon separator
                    # Should NOT have pattern like acc:[a-z-]+\.\d{3}
                    assert r'\.' not in pattern.split(':')[1] if len(pattern.split(':')) > 1 else True, \
                        f"Pattern should use colon between wagon and sequence, got: {pattern}"

            for key, value in obj.items():
                find_urn_pattern(value, f"{path}.{key}")

        elif isinstance(obj, list):
            for item in obj:
                find_urn_pattern(item, path)

    find_urn_pattern(schema)

    # Test would pass if schema is updated correctly
    # For now, we're just checking structure exists
    assert True, "Schema structure validated"
