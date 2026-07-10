# URN: test:coach:urn:extension_contract
"""
Substrate URN-extension contract (issue #421).

Demonstrates that introducing a new URN family requires only:

  (a) a new resolver class in resolver.py
  (b) a new ROW in the URN grammar convention (``urn_grammar.yaml``) — its
      ``pattern`` + ``segment_count`` are projected into ``URNGrammar.PATTERNS``
      / ``SEGMENT_COUNTS`` at import (issue #1421); the engine is unchanged
  (c) nothing in ``URNGrammar.parse_urn`` for a colon-only family — parsing is
      driven by the convention's ``segments`` names
  (d) optionally a builder method on URNGrammar

— and NO edits to validators, CLI subcommand registries, test discovery,
graph builders, or any other call site.

The test installs a throwaway ``theatre:`` URN family behind a pytest
fixture (the "test-only flag") by adding one convention row to a copy of the
loaded grammar and reprojecting the class tables exactly as ``URNGrammar`` does
at import — mirroring the production extension steps without permanently
altering shipped data. The assertions then prove that:

- The registry recognises the new family (``ResolverRegistry.families``).
- ``URNGrammar.PATTERNS`` validates the new URN.
- ``URNGrammar.validate_grammar`` auto-detects the new family using the
  registered SEGMENT_COUNTS entry.
- ``EdgeValidator`` runs cleanly on a graph containing the new family
  (no crash, no false-positive orphan or missing-edge issue).
- The CLI families helper iterates the registry — no changes to the
  argparse subcommand definitions required.

Audit report: ``docs/urn-prefix-audit-2026.md``.
"""

from __future__ import annotations

import pytest

from atdd.coach.utils.graph.edge_validator import EdgeValidator
from atdd.coach.utils.graph.graph_builder import TraceabilityGraph, URNNode
from atdd.coach.utils.graph.resolver import (
    BaseResolver,
    ResolverRegistry,
    URNResolution,
)
from atdd.coach.utils.graph.urn import URNGrammar


# ---------------------------------------------------------------------------
# (b) Test-only flag: add ONE theatre: convention row and reproject the tables.
# ---------------------------------------------------------------------------
@pytest.fixture
def theatre_pattern_installed(monkeypatch):
    """Install a ``theatre:<slug>`` family for the duration of one test.

    Convention-native (issue #1421): a family is one row of grammar data. This
    adds that row to a copy of the loaded ``_FAMILY_SPECS`` and reprojects
    ``PATTERNS`` / ``SEGMENT_COUNTS`` the same way ``URNGrammar`` does at import
    — proving a new family is a one-row convention edit, with no engine change.
    """
    theatre_row = {
        "pattern": r"^theatre:[a-z][a-z0-9-]*$",
        "segment_count": 1,  # parent-it-belongs-to: top-level root (no parent)
        "parent": None,
        "segments": ["slug"],
    }
    new_specs = dict(URNGrammar._FAMILY_SPECS)
    new_specs["theatre"] = theatre_row
    monkeypatch.setattr(URNGrammar, "_FAMILY_SPECS", new_specs)
    monkeypatch.setattr(
        URNGrammar,
        "PATTERNS",
        {family: spec["pattern"] for family, spec in new_specs.items()},
    )
    monkeypatch.setattr(
        URNGrammar,
        "SEGMENT_COUNTS",
        {
            family: spec["segment_count"]
            for family, spec in new_specs.items()
            if spec.get("segment_count") is not None
        },
    )


# ---------------------------------------------------------------------------
# (a) Throwaway resolver class.
# ---------------------------------------------------------------------------
class TheatreResolver(BaseResolver):
    """Stand-in resolver for the throwaway ``theatre:`` URN family."""

    @property
    def family(self) -> str:
        return "theatre"

    def resolve(self, urn: str) -> URNResolution:
        if not self.can_resolve(urn):
            return URNResolution(urn=urn, family=self.family, error="Not a theatre URN")
        return URNResolution(
            urn=urn,
            family=self.family,
            resolved_paths=[],  # virtual — test-only
            is_deterministic=True,
            error=None,
        )

    def find_declarations(self):
        return []


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
def test_a_resolver_registration_exposes_family(theatre_pattern_installed, tmp_path):
    """(a): registering TheatreResolver puts ``theatre`` in registry.families
    without editing ResolverRegistry._register_default_resolvers."""
    registry = ResolverRegistry(repo_root=tmp_path)
    registry.register(TheatreResolver(repo_root=tmp_path))

    assert "theatre" in registry.families
    # Existing families still present
    assert "wagon" in registry.families
    assert "security" in registry.families


def test_b_patterns_entry_validates_new_urn(theatre_pattern_installed):
    """(b): adding a single PATTERNS entry is enough for validate_urn /
    validate_grammar to accept the new URN."""
    assert URNGrammar.validate_urn("theatre:hamlet", "theatre")
    assert URNGrammar.validate_grammar("theatre:hamlet")


def test_b_grammar_rejects_malformed_theatre_urn(theatre_pattern_installed):
    """validate_grammar surfaces a clear segment-count error from
    SEGMENT_COUNTS — no per-family error code required."""
    # Two tokens after prefix, but theatre: has segment_count == 1.
    with pytest.raises(ValueError, match="wrong segment count"):
        URNGrammar.validate_grammar("theatre:hamlet:act-1")


def test_no_validator_edits_required(theatre_pattern_installed, tmp_path):
    """The two principal validators (orphan check, edge completeness) must
    handle theatre: nodes without crashes or false positives — proving the
    closed enumerations in edge_validator.py are intentionally opt-in,
    not blockers for new families."""
    registry = ResolverRegistry(repo_root=tmp_path)
    registry.register(TheatreResolver(repo_root=tmp_path))

    graph = TraceabilityGraph()
    graph.add_node(URNNode(urn="theatre:hamlet", family="theatre"))

    validator = EdgeValidator(graph)

    # Orphan check skips families outside _non_orphan_families — no false positive
    orphans = validator.find_orphans()
    assert all(o.urn != "theatre:hamlet" for o in orphans)

    # validate_edges has no theatre: branch — node simply skipped, no crash
    edge_issues = validator.validate_edges()
    assert all(i.urn != "theatre:hamlet" for i in edge_issues)

    # validate_all runs end-to-end with the new family in the graph
    result = validator.validate_all()
    assert result.checked_urns >= 1


def test_no_cli_subcommand_registry_edits_required(theatre_pattern_installed, tmp_path):
    """The CLI ``atdd repo families`` command iterates ResolverRegistry.families
    — the new family appears with no argparse / subcommand-table edits."""
    registry = ResolverRegistry(repo_root=tmp_path)
    registry.register(TheatreResolver(repo_root=tmp_path))

    # Mirrors atdd/coach/commands/urn.py::URNCommand.list_families
    listed = sorted(registry.families)
    assert "theatre" in listed


def test_no_test_discovery_edits_required(theatre_pattern_installed, tmp_path):
    """find_all_declarations dispatches per-family by iterating the registry;
    no test-discovery code names theatre: explicitly."""
    registry = ResolverRegistry(repo_root=tmp_path)
    registry.register(TheatreResolver(repo_root=tmp_path))

    declarations = registry.find_all_declarations()
    # The new family is present (empty list — TheatreResolver returns no decls
    # in this test-only setup), proving discovery does not gate on a closed list.
    assert "theatre" in declarations
    assert declarations["theatre"] == []
