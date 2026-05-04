# URN: component:govern-lifecycle:enforcement-substrate:test_rule_id_legacy_grammar:backend:domain
# Runtime: python
# Purpose: RED tests for legacy_grammar acceptance in rule-id uniqueness validator.

"""RED tests for issue #389 Phase 1: legacy_grammar extension.

What this file covers:

1. ``rule-id.convention.yaml`` declares ``legacy_grammar:`` enumerating the
   3 pre-#340 ID shapes (DS-NN, ERR-NN, GP-NN) with one-line rationale per
   variant — Decision #8 explicitly excludes AP-DS-NN and COACH-BABYSIT-NNN
   because they already match the canonical grammar.
2. The validator's ``validate_grammar`` accepts a legacy-pattern set so an
   ID matching a legacy variant passes when its declaring file is in
   ``migration.completed:``.
3. The uniqueness check operates across both canonical and legacy grammars,
   but only counts a legacy-shaped ID when its file is migrated.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from atdd.coach.validators.test_rule_id_uniqueness import (
    extract_rules,
    load_allowed_domains,
    load_rule_id_convention,
    validate_grammar,
)


# ---------------------------------------------------------------------------
# Convention shape: legacy_grammar block
# ---------------------------------------------------------------------------

class TestLegacyGrammarSection:
    def test_section_present(self):
        data = load_rule_id_convention()
        assert "legacy_grammar" in data, (
            "rule-id.convention.yaml must declare legacy_grammar: per issue #389 Phase 1"
        )

    def test_section_is_list_of_entries(self):
        data = load_rule_id_convention()
        legacy = data.get("legacy_grammar")
        assert isinstance(legacy, list) and len(legacy) >= 3, (
            "legacy_grammar: must enumerate at least 3 variants (DS-NN, ERR-NN, GP-NN)"
        )
        for entry in legacy:
            assert isinstance(entry, dict), f"each entry must be a mapping, got {entry!r}"
            assert "pattern" in entry and isinstance(entry["pattern"], str), (
                f"entry missing string `pattern`: {entry!r}"
            )
            assert "rationale" in entry and isinstance(entry["rationale"], str) and entry["rationale"].strip(), (
                f"entry missing non-empty string `rationale`: {entry!r}"
            )

    @pytest.mark.parametrize("expected_pattern", [
        r"^DS-\d{2}$",
        r"^ERR-\d{2}$",
        r"^GP-\d{2}$",
    ])
    def test_required_variants_declared(self, expected_pattern):
        data = load_rule_id_convention()
        patterns = {e.get("pattern") for e in (data.get("legacy_grammar") or [])}
        assert expected_pattern in patterns, (
            f"legacy_grammar must include {expected_pattern!r} per issue #389 Phase 1 scope"
        )

    def test_excludes_ap_ds_and_coach_babysit(self):
        """Decision #8: AP-DS-NN and COACH-BABYSIT-NNN already match canonical, must not appear in legacy_grammar."""
        data = load_rule_id_convention()
        patterns = {e.get("pattern") for e in (data.get("legacy_grammar") or [])}
        for forbidden in (r"^AP-DS-\d{2}$", r"^COACH-BABYSIT-\d{3}$"):
            assert forbidden not in patterns, (
                f"{forbidden!r} must not be in legacy_grammar — Decision #8: already canonical"
            )


# ---------------------------------------------------------------------------
# Helper: legacy pattern loader
# ---------------------------------------------------------------------------

class TestLoadLegacyPatterns:
    def test_loader_exposed(self):
        """Validator module exposes load_legacy_patterns() returning compiled regexes."""
        from atdd.coach.validators import test_rule_id_uniqueness as mod
        assert hasattr(mod, "load_legacy_patterns"), (
            "test_rule_id_uniqueness must expose load_legacy_patterns()"
        )
        patterns = mod.load_legacy_patterns()
        assert isinstance(patterns, list) and patterns, "must return non-empty list"
        for p in patterns:
            assert isinstance(p, re.Pattern), f"expected re.Pattern, got {type(p).__name__}"

    def test_legacy_ids_match(self):
        from atdd.coach.validators.test_rule_id_uniqueness import load_legacy_patterns
        patterns = load_legacy_patterns()

        def matches_any(rid: str) -> bool:
            return any(p.match(rid) for p in patterns)

        for rid in ("DS-01", "DS-07", "ERR-01", "ERR-12", "GP-01", "GP-99"):
            assert matches_any(rid), f"legacy ID {rid!r} should match a legacy pattern"

    def test_canonical_ids_dont_match_legacy(self):
        """Post-#399 canonical (namespaced) IDs must not match any legacy pattern."""
        from atdd.coach.validators.test_rule_id_uniqueness import load_legacy_patterns
        patterns = load_legacy_patterns()
        for rid in (
            "coder.green.urn",
            "coach.rule-id.binding",
            "tester.smoke.harness-subprocess-failed-crash",
        ):
            assert not any(p.match(rid) for p in patterns), (
                f"canonical namespaced ID {rid!r} must not match a legacy pattern"
            )


# ---------------------------------------------------------------------------
# validate_grammar gains optional legacy_patterns acceptance
# ---------------------------------------------------------------------------

class TestValidateGrammarLegacy:
    def test_signature_accepts_legacy_patterns_kwarg(self):
        domains = load_allowed_domains()
        # Default behavior unchanged: legacy not accepted.
        assert validate_grammar("DS-01", domains) is not None
        # Opt-in: legacy accepted.
        assert validate_grammar("DS-01", domains, legacy_patterns=[re.compile(r"^DS-\d{2}$")]) is None

    def test_canonical_still_accepted_with_legacy_kwarg(self):
        """A canonical namespaced ID is accepted regardless of legacy_patterns."""
        domains = load_allowed_domains()
        legacy = [re.compile(r"^DS-\d{2}$")]
        assert validate_grammar("coder.green.urn", domains, legacy_patterns=legacy) is None

    def test_unknown_id_rejected_with_legacy_kwarg(self):
        domains = load_allowed_domains()
        legacy = [re.compile(r"^DS-\d{2}$")]
        # Not legacy, not canonical — must still be rejected.
        assert validate_grammar("XYZ-99", domains, legacy_patterns=legacy) is not None


# ---------------------------------------------------------------------------
# extract_rules: walks legacy IDs too (for uniqueness across both grammars)
# ---------------------------------------------------------------------------

class TestUniquenessAcrossLegacyAndCanonical:
    def test_uniqueness_walks_legacy_in_migrated_files(self, tmp_path: Path, monkeypatch):
        """A legacy DS-01 in a migrated file collides with another DS-01 elsewhere."""
        from atdd.coach.validators import test_rule_id_uniqueness as mod

        migrated = tmp_path / "migrated.convention.yaml"
        migrated.write_text(
            "design_system:\n"
            "  rules:\n"
            "    - id: DS-01\n"
            "      severity: 2\n"
            "      description: legacy\n"
        )
        other = tmp_path / "other.convention.yaml"
        other.write_text(
            "design_system:\n"
            "  rules:\n"
            "    - id: DS-01\n"
            "      severity: 2\n"
            "      description: legacy collision\n"
        )

        monkeypatch.setattr(mod, "find_convention_files", lambda: [migrated, other])
        monkeypatch.setattr(mod, "load_migrated_files", lambda: [migrated.resolve(), other.resolve()])

        with pytest.raises(pytest.fail.Exception) as exc:
            mod.test_rule_id_uniqueness()

        # The collision detection should mention DS-01.
        assert "DS-01" in str(exc.value), f"expected DS-01 collision in error: {exc.value}"
