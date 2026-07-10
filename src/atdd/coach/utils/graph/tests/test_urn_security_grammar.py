# URN: test:coach:urn:security_grammar
"""
Coverage for spec v12 §3.2 (parent-it-belongs-to URN grammar).

Issue #420 ships the ``security:<wagon>:<feature-slug>:<NNN>`` URN family
(parent = feature, 3 tokens) plus the segment-count table that anchors the
parent-it-belongs-to principle. These tests pin both behaviors so a future
refactor cannot silently drift either:

- The new ``URNGrammar.security`` builder, ``parse_urn`` parser, and
  ``validate_urn`` regex round-trip every documented form (digit-string,
  ``THREAT-N``, padded numeric, int).
- The ``validate_grammar`` auto-detect entry point fails with a clear,
  actionable error when a known prefix has the wrong segment count, and a
  separate "unknown resource type" error when the prefix is not registered.
- ``URNGrammar.SEGMENT_COUNTS`` and ``URNGrammar.PATTERNS`` stay in lockstep
  with the spec §3.2 table — the parametrized test below guards both the
  numeric counts and the regex segment counts at once.

Naming follows filename.convention.yaml: test_{component}_{what}.py.
"""

from __future__ import annotations

import pytest

from atdd.coach.utils.graph.urn import URNGrammar


# ---------------------------------------------------------------------------
# security:<wagon>:<feature-slug>:<NNN> — builder + parser + validator
# ---------------------------------------------------------------------------


class TestSecurityBuilder:
    """URNGrammar.security() builds canonical 3-token security URNs."""

    def test_canonical_inputs_round_trip(self):
        urn = URNGrammar.security("auth", "session-management", "001")
        assert urn == "security:auth:session-management:001"
        assert URNGrammar.validate_urn(urn, "security") is True

        parsed = URNGrammar.parse_urn(urn)
        assert parsed == {
            "type": "security",
            "wagon_id": "auth",
            "feature_id": "session-management",
            "threat_seq": "001",
        }

    @pytest.mark.parametrize(
        "given,expected",
        [
            ("THREAT-1", "001"),       # spec example — issue body
            ("THREAT-42", "042"),      # spec example — issue body
            ("THREAT-001", "001"),     # spec example — already padded
            ("threat-7", "007"),       # case-insensitive
            ("threat_3", "003"),       # underscore separator tolerated
            ("THREAT123", "123"),      # no separator at all
            ("42", "042"),             # bare digit string padded
            ("999", "999"),            # upper bound
            ("1", "001"),              # lower bound
            (1, "001"),                # int input
            (42, "042"),               # int input
            (999, "999"),              # int input upper bound
        ],
    )
    def test_threat_seq_normalization(self, given, expected):
        urn = URNGrammar.security("auth", "session-management", given)
        assert urn == f"security:auth:session-management:{expected}"

    @pytest.mark.parametrize("bad_seq", [0, 1000, -1, "0", "1000", "THREAT-1000"])
    def test_threat_seq_out_of_range_rejected(self, bad_seq):
        with pytest.raises(ValueError, match="between 1 and 999"):
            URNGrammar.security("auth", "session-management", bad_seq)

    @pytest.mark.parametrize("bad_seq", ["", "abc", "THREAT-", "001a", "THREAT-x1"])
    def test_threat_seq_malformed_rejected(self, bad_seq):
        with pytest.raises(ValueError):
            URNGrammar.security("auth", "session-management", bad_seq)

    def test_threat_seq_bool_rejected(self):
        # bool is a subclass of int — explicitly reject so True/False never
        # silently round-trips to "001"/"000".
        with pytest.raises(TypeError):
            URNGrammar.security("auth", "session-management", True)

    # Note: ``_normalize_id`` lowercases, strips leading/trailing hyphens, and
    # collapses underscores → hyphens BEFORE the regex check. So inputs like
    # "Auth" or "-auth" are normalized to "auth" and accepted by design. Only
    # truly unfixable inputs (empty, leading-digit, embedded punctuation) hit
    # the validator branch.
    @pytest.mark.parametrize("bad_wagon", ["", "1auth", "auth!"])
    def test_invalid_wagon_id_rejected(self, bad_wagon):
        with pytest.raises(ValueError, match="(?i)wagon"):
            URNGrammar.security(bad_wagon, "session-management", "001")

    @pytest.mark.parametrize("bad_slug", ["", "1session", "session!"])
    def test_invalid_feature_slug_rejected(self, bad_slug):
        with pytest.raises(ValueError, match="(?i)feature slug"):
            URNGrammar.security("auth", bad_slug, "001")


# ---------------------------------------------------------------------------
# validate_urn / parse_urn — regex pass/fail and parser symmetry
# ---------------------------------------------------------------------------


class TestSecurityValidatorAndParser:
    @pytest.mark.parametrize(
        "good_urn",
        [
            "security:auth:session-management:001",
            "security:checkout:cart-overflow:042",
            "security:a:b:999",  # minimal slugs
            "security:auth-service:multi-factor-auth:007",
        ],
    )
    def test_valid_security_urns_pass(self, good_urn):
        assert URNGrammar.validate_urn(good_urn, "security") is True
        assert URNGrammar.validate_grammar(good_urn) is True

    @pytest.mark.parametrize(
        "bad_urn",
        [
            "security:auth:session-management",          # only 2 tokens
            "security:auth:session-management:1",        # not zero-padded
            "security:auth:session-management:0001",     # too many digits
            "security:auth:session-management:abc",      # non-numeric seq
            "security:Auth:session-management:001",      # uppercase wagon
            "security::session-management:001",          # empty wagon
            "security:auth::001",                        # empty feature slug
            "security:auth:session-management:001:extra",  # 4 tokens
        ],
    )
    def test_invalid_security_urns_fail_validate_urn(self, bad_urn):
        assert URNGrammar.validate_urn(bad_urn, "security") is False

    def test_parse_security_urn_returns_named_components(self):
        parsed = URNGrammar.parse_urn(
            "security:checkout:cart-overflow:042"
        )
        assert parsed["type"] == "security"
        assert parsed["wagon_id"] == "checkout"
        assert parsed["feature_id"] == "cart-overflow"
        assert parsed["threat_seq"] == "042"

    def test_parse_security_urn_wrong_segment_count_raises(self):
        with pytest.raises(ValueError, match="segment count"):
            URNGrammar.parse_urn("security:checkout:only-two-tokens")


# ---------------------------------------------------------------------------
# validate_grammar — parent-it-belongs-to auto-detect entry point
# ---------------------------------------------------------------------------


class TestValidateGrammar:
    """The auto-detecting validator that operationalizes spec §3.2."""

    def test_known_prefix_correct_segment_count_passes(self):
        assert URNGrammar.validate_grammar("wagon:auth") is True
        assert URNGrammar.validate_grammar("feature:auth:session") is True
        assert URNGrammar.validate_grammar("wmbt:auth:E001") is True
        assert URNGrammar.validate_grammar(
            "security:auth:session-management:001"
        ) is True

    @pytest.mark.parametrize(
        "bad_urn,expected_count",
        [
            # Too few tokens for the family
            ("security:auth:only-two", 3),
            # Too many tokens for the family
            ("security:auth:session-management:001:extra", 3),
            ("feature:auth:session:extra", 2),
            ("wmbt:auth:E001:extra", 2),
            ("wagon:auth:extra", 1),
        ],
    )
    def test_known_prefix_wrong_segment_count_raises_with_named_resource(
        self, bad_urn, expected_count
    ):
        prefix = bad_urn.split(":", 1)[0]
        with pytest.raises(ValueError) as exc:
            URNGrammar.validate_grammar(bad_urn)

        msg = str(exc.value)
        # Error must name the resource and the expected count so the user
        # can fix it without reading the spec PDF.
        assert prefix in msg, f"resource name missing from {msg!r}"
        assert str(expected_count) in msg, f"expected count missing from {msg!r}"
        assert "parent-it-belongs-to" in msg or "segment count" in msg

    def test_unknown_resource_type_raises_explicit_error(self):
        with pytest.raises(ValueError, match="unknown resource type"):
            URNGrammar.validate_grammar("zaphod:auth:beeblebrox")

    def test_malformed_urn_without_prefix_raises(self):
        with pytest.raises(ValueError, match="(?i)malformed|prefix"):
            URNGrammar.validate_grammar("not-a-urn-at-all")


# ---------------------------------------------------------------------------
# SEGMENT_COUNTS table — must stay in lockstep with PATTERNS and the spec
# ---------------------------------------------------------------------------


# Verbatim mirror of spec v12 §3.2 table. Each entry pairs the family name
# with (a) the documented post-prefix token count and (b) a representative
# canonical URN. The sample URN has to validate via the family's regex AND
# present exactly N colon-separated tokens after the prefix — both halves of
# the parent-it-belongs-to contract verified at once.
#
# When a new family is added, register it here AND in ``URNGrammar.PATTERNS``
# / ``URNGrammar.SEGMENT_COUNTS`` — this test will fail loudly if any of the
# three drift apart.
SPEC_3_2_TABLE = [
    # (resource, expected_token_count_after_prefix, sample_urn)
    ("wagon",    1, "wagon:auth"),
    # train is now TYPED (issue #1421): train:<subject>:<slug>, 2 tokens,
    # parented by the 1-token root ``subject:`` family. ``category`` is a field,
    # not an identity digit; the legacy ``train:NNNN-slug`` form is retired.
    ("subject",  1, "subject:artifact-identity"),
    ("train",    2, "train:artifact-identity:migrate-with-alias"),
    ("feature",  2, "feature:auth:session-management"),
    ("wmbt",     2, "wmbt:auth:E001"),
    ("acc",      2, "acc:auth:E001-UNIT-001"),
    ("security", 3, "security:auth:session-management:001"),
]


@pytest.mark.parametrize("resource,expected_count,sample_urn", SPEC_3_2_TABLE)
def test_urn_segment_count_table(resource, expected_count, sample_urn):
    """SEGMENT_COUNTS, PATTERNS, and spec §3.2 stay in lockstep."""
    # 1. SEGMENT_COUNTS matches the spec.
    assert URNGrammar.SEGMENT_COUNTS[resource] == expected_count, (
        f"SEGMENT_COUNTS[{resource!r}] does not match spec §3.2"
    )

    # 2. PATTERNS has an entry for this family.
    assert resource in URNGrammar.PATTERNS, (
        f"{resource!r} declared in SEGMENT_COUNTS but missing from PATTERNS"
    )

    # 3. The canonical sample URN is regex-valid for this family.
    assert URNGrammar.validate_urn(sample_urn, resource), (
        f"sample URN {sample_urn!r} does not validate as {resource!r}"
    )

    # 4. The canonical sample URN's actual token count matches the spec.
    actual_tokens = len(sample_urn.split(":")) - 1
    assert actual_tokens == expected_count, (
        f"sample URN {sample_urn!r} has {actual_tokens} tokens after prefix, "
        f"spec §3.2 requires {expected_count}"
    )

    # 5. validate_grammar() (the auto-detect entry point) accepts the sample.
    assert URNGrammar.validate_grammar(sample_urn) is True


def test_segment_counts_covers_documented_families():
    """Every family in SPEC_3_2_TABLE must be declared in SEGMENT_COUNTS."""
    documented = {name for name, _, _ in SPEC_3_2_TABLE}
    declared = set(URNGrammar.SEGMENT_COUNTS)
    missing = documented - declared
    assert not missing, f"SEGMENT_COUNTS missing spec §3.2 families: {missing}"
