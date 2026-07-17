# URN: component:govern-lifecycle:enforcement-substrate:test_phase_3a_rules_array_coverage:backend:domain
# Runtime: python
# Purpose: RED tests for issue #389 Phase 3a — every targeted convention declares a rules: array.

"""RED tests for issue #389 Phase 3a: rules-array coverage in 7 conventions.

The registry walker (#387) walks ``rules:`` arrays at any nesting depth
(Decision #9). These 7 coder+coach conventions previously lacked any
``rules:`` block; this issue retrofits them.

The structured rules added here use canonical ``<DOMAIN>-<TOPIC>-<NNN>``
grammar so the uniqueness check (which walks every convention) accepts them
without requiring strict-mode opt-in (Phase 3b is out of scope for this PR).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

import atdd
from atdd.coach.utils.repo import find_repo_root
from atdd.coach.validators.test_rule_id_uniqueness import (
    RULE_ID_PATTERN,
    extract_rules,
    load_allowed_domains,
    validate_description,
    validate_grammar,
    validate_severity,
)

# Toolkit dogfood: asserts on toolkit-only repo content (#1475).
pytestmark = [pytest.mark.platform]


ATDD_PKG_DIR = Path(atdd.__file__).resolve().parent


# Issue #389 Phase 3a inventory (verbatim from issue body).
PHASE_3A_FILES = [
    "coder/conventions/backend.convention.yaml",
    "coder/conventions/commons.convention.yaml",
    "coder/conventions/design.convention.yaml",
    "coder/conventions/presentation.convention.yaml",
    # technology.convention.yaml: its governance rules were atomized into single-node
    # nodes/coder.technology.*.convention.yaml (Phase A decomposition); the monolith
    # now carries only the (extension-bound) stack tree. The rules-array requirement
    # is satisfied by the nodes/ home (verified by no-orphan + registry), so the
    # monolith file is no longer in this retrofit list.
    #
    # train.convention.yaml: its three COACH-TRAIN-COMPOSITION-001/002/003 rules were
    # collapsed into nodes/coder.train.production-composition-cargo-zero-drift.convention.yaml
    # (#1218 careful pass); the monolith now carries only prose (composition_hierarchy,
    # train_structure, cargo_pattern, ...) preserved as migration source. Same as
    # technology above, the nodes/ home satisfies the rules requirement, so the monolith
    # is no longer in this retrofit list.
    "coach/conventions/naming.convention.yaml",
]


def _resolve(rel: str) -> Path:
    """Resolve a convention path against the repo or installed package."""
    for cand in (find_repo_root() / "src" / "atdd" / rel, ATDD_PKG_DIR / rel):
        if cand.is_file():
            return cand
    raise FileNotFoundError(f"convention not found: {rel}")


# ---------------------------------------------------------------------------
# Each Phase 3a convention declares at least one structured rule
# ---------------------------------------------------------------------------

class TestRulesArrayPresence:
    @pytest.mark.parametrize("rel", PHASE_3A_FILES)
    def test_convention_has_structured_rules(self, rel):
        path = _resolve(rel)
        rows = extract_rules(path)
        assert rows, (
            f"{rel} must declare a `rules:` array (top-level or nested) per "
            f"issue #389 Phase 3a — Decision #9 says the walker recurses, so "
            f"placement may be next to existing rule-bearing structure."
        )


# ---------------------------------------------------------------------------
# All Phase 3a rules use canonical grammar with valid severity + description
# ---------------------------------------------------------------------------

class TestPhase3aRuleQuality:
    @pytest.mark.parametrize("rel", PHASE_3A_FILES)
    def test_each_rule_well_formed(self, rel):
        domains = load_allowed_domains()
        path = _resolve(rel)
        errors = []
        for _, yaml_path, rule in extract_rules(path):
            loc = f"{path.name}:{'.'.join(yaml_path[:-1])}[{yaml_path[-1]}]"
            for check in (
                validate_grammar(rule.get("id", ""), domains),
                validate_severity(rule),
                validate_description(rule),
            ):
                if check:
                    errors.append(f"{loc}: {check}")
        assert not errors, "rule shape errors:\n  - " + "\n  - ".join(errors)


# ---------------------------------------------------------------------------
# Existing id-bearing structures (principles/anti_patterns/...) are preserved
# ---------------------------------------------------------------------------

class TestExistingStructuresPreserved:
    """Issue body: 'Existing id-bearing structures... are preserved verbatim'.

    Spot-check: design.convention.yaml keeps its DS-NN principles and AP-DS-NN
    anti_patterns; commons keeps dependency_rules; backend keeps entrypoint_rules.
    """

    def test_design_principles_intact(self):
        path = _resolve("coder/conventions/design.convention.yaml")
        data = yaml.safe_load(path.read_text())
        principles = (data.get("design_system") or {}).get("principles") or []
        ids = {p.get("id") for p in principles if isinstance(p, dict)}
        assert {"DS-01", "DS-02", "DS-03", "DS-04", "DS-05", "DS-06", "DS-07"}.issubset(ids), (
            f"design.convention.yaml principles must keep DS-01..DS-07; got {sorted(ids)}"
        )

    def test_design_anti_patterns_intact(self):
        path = _resolve("coder/conventions/design.convention.yaml")
        data = yaml.safe_load(path.read_text())
        antis = (data.get("design_system") or {}).get("anti_patterns") or []
        ids = {a.get("id") for a in antis if isinstance(a, dict)}
        assert {"AP-DS-01", "AP-DS-02", "AP-DS-03", "AP-DS-04", "AP-DS-05"}.issubset(ids), (
            f"design.convention.yaml anti_patterns must keep AP-DS-01..AP-DS-05; got {sorted(ids)}"
        )

    def test_commons_dependency_rules_intact(self):
        path = _resolve("coder/conventions/commons.convention.yaml")
        data = yaml.safe_load(path.read_text())
        assert "dependency_rules" in data, "commons.convention.yaml must keep dependency_rules:"
