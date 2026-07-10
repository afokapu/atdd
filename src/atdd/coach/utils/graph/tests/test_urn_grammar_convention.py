# URN: test:coach:urn:grammar_convention
"""
Convention-native URN grammar engine (issue #1421).

The URN grammar used to be hard-coded in ``URNGrammar.PATTERNS`` /
``SEGMENT_COUNTS`` — the one grammar engine in ATDD that never got wired to a
convention, a standing drift generator against ATDD's *executable conventions*
thesis. These tests pin the corrected behaviour: the engine now *reads* its
grammar from a data convention (the ``verb_lexicon`` pattern), exactly one
source, and gains two new families the old hard-coded table could not express:

- ``subject:<name>`` — a 1-token **root** family (the durable noun object of a
  train's change), so a 2-token typed train is not orphaned by the graph model.
- ``train:<subject>:<slug>`` — the **typed** train identity. ``category`` is a
  field, never an identity digit; the legacy ``train:NNNN-slug`` form no longer
  validates in the engine grammar (legacy resolution is the resolver's job).

Cycle safety: the engine reads the grammar with plain ``yaml`` + ``pathlib`` +
``@lru_cache`` (never through ``bind_rule`` / the convention-graph loader), the
same discipline that keeps ``verb_lexicon`` cycle-free — ``urn.py`` still
imports zero atdd modules.
"""

from __future__ import annotations

import pytest

from atdd.coach.utils.graph import urn as urn_mod
from atdd.coach.utils.graph.urn import URNGrammar


# ---------------------------------------------------------------------------
# (a) The engine sources PATTERNS / SEGMENT_COUNTS from the convention YAML.
# ---------------------------------------------------------------------------
class TestGrammarIsConventionSourced:
    def test_loader_reads_families_from_yaml(self):
        families = urn_mod._load_grammar_families()
        # Data lift preserved every historical family verbatim.
        assert "wagon" in families
        assert families["wagon"]["pattern"] == r"^wagon:[a-z][a-z0-9-]*$"
        # The class attributes are projections of that single source.
        assert URNGrammar.PATTERNS["wagon"] == families["wagon"]["pattern"]

    def test_segment_counts_projected_from_convention(self):
        families = urn_mod._load_grammar_families()
        assert URNGrammar.SEGMENT_COUNTS["security"] == families["security"]["segment_count"]

    def test_grammar_yaml_read_without_atdd_imports(self):
        # Cycle-free discipline: the module must not reach for the convention
        # graph loader / bind_rule to read its own grammar.
        src = (urn_mod.__file__)
        text = open(src, encoding="utf-8").read()
        assert "bind_rule" not in text
        assert "rule_binding" not in text
        assert "convention_loader" not in text


# ---------------------------------------------------------------------------
# (b) subject: is a first-class root family.
# ---------------------------------------------------------------------------
class TestSubjectFamily:
    def test_subject_is_a_root_family(self):
        assert URNGrammar.SEGMENT_COUNTS["subject"] == 1

    def test_subject_validates(self):
        assert URNGrammar.validate_urn("subject:artifact-identity", "subject") is True
        assert URNGrammar.validate_grammar("subject:artifact-identity") is True

    def test_subject_builder_round_trips(self):
        urn = URNGrammar.subject("artifact-identity")
        assert urn == "subject:artifact-identity"
        assert URNGrammar.validate_grammar(urn) is True

    def test_subject_rejects_two_tokens(self):
        with pytest.raises(ValueError, match="segment count"):
            URNGrammar.validate_grammar("subject:artifact-identity:extra")


# ---------------------------------------------------------------------------
# (c) train: is typed (train:<subject>:<slug>); the NNNN-slug form is retired.
# ---------------------------------------------------------------------------
class TestTypedTrainFamily:
    def test_typed_train_validates(self):
        assert URNGrammar.validate_urn(
            "train:artifact-identity:migrate-with-alias", "train"
        ) is True
        assert URNGrammar.validate_grammar(
            "train:artifact-identity:migrate-with-alias"
        ) is True

    def test_train_is_two_tokens_parented_by_subject(self):
        assert URNGrammar.SEGMENT_COUNTS["train"] == 2
        families = urn_mod._load_grammar_families()
        assert families["train"]["parent"] == "subject"

    def test_legacy_numeric_train_no_longer_validates(self):
        assert URNGrammar.validate_urn("train:0008-x", "train") is False
        with pytest.raises(ValueError):
            URNGrammar.validate_grammar("train:0008-x")

    def test_train_builder_and_parse_round_trip(self):
        urn = URNGrammar.train("artifact-identity", "migrate-with-alias")
        assert urn == "train:artifact-identity:migrate-with-alias"
        parsed = URNGrammar.parse_urn(urn)
        assert parsed == {
            "type": "train",
            "subject": "artifact-identity",
            "slug": "migrate-with-alias",
        }


# ---------------------------------------------------------------------------
# (d) validate / parse / build all round-trip through the one convention source.
# ---------------------------------------------------------------------------
class TestEnginePathsRoundTripViaConvention:
    def test_build_validate_parse_security(self):
        urn = URNGrammar.security("auth", "session-management", "001")
        assert URNGrammar.validate_grammar(urn) is True
        assert URNGrammar.parse_urn(urn) == {
            "type": "security",
            "wagon_id": "auth",
            "feature_id": "session-management",
            "threat_seq": "001",
        }

    def test_build_validate_parse_feature(self):
        urn = URNGrammar.feature("manage-users", "authenticate-user")
        assert URNGrammar.validate_grammar(urn) is True
        assert URNGrammar.parse_urn(urn) == {
            "type": "feature",
            "wagon_id": "manage-users",
            "feature_id": "authenticate-user",
        }

    def test_parse_is_segment_driven_not_hardcoded(self):
        # Component parsing maps colon tokens to the convention's `segments`
        # names — no per-family branch required in the engine.
        parsed = URNGrammar.parse_urn(
            "component:user-mgmt:auth:LoginForm:frontend:presentation"
        )
        assert parsed["wagon_id"] == "user-mgmt"
        assert parsed["feature_id"] == "auth"
        assert parsed["component_name"] == "LoginForm"
        assert parsed["side"] == "frontend"
        assert parsed["layer"] == "presentation"
