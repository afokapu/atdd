# URN: test:validate-conventions:coverage-variants:wmbt_has_smoke_acceptance
# WMBT: wmbt:validate-conventions:E010
# Phase: GREEN
# Layer: integration
# Assertion: behavioral
"""Convention validator variant `coverage/wmbt_has_smoke_acceptance` (#1206 / #1212).

Instantiates the `coverage/source_has_required_target` template against the composed convention
graph. Every WMBT must declare >=1 acceptance carrying the SMOKE harness token;
inline-suppressed WMBTs (legacy `suppress-and-clean` disposition) are skipped so
the clean repo stays at 0.

Legacy parity: BOTH catch. The legacy `test_every_wmbt_has_smoke_acceptance`
enforces via the disposition gate; the fault-injection test below proves the
convention evaluator and the legacy validator both flag the same injected fault.
"""
from __future__ import annotations

from atdd.validators.conventions.coverage.archetype import (
    TEMPLATE_IDS,
    _source_has_required_target,
)
from atdd.validators.conventions.coverage import _parity

FAMILY = "coverage"
TEMPLATE = "source_has_required_target"
VARIANT = "wmbt_has_smoke_acceptance"
QUESTION = 'For every source node of type X, does required downstream target Y exist?'
SELECTOR = 'nodes where node.coverage.requires exists'
TRAVERSAL = 'source node -> required relationship/path -> target node set'
INVARIANT = 'target set is non-empty and satisfies required target kind/filter'
AUTO_CAPTURE = 'a new node is included if it declares coverage requirements'
FAILURE_EVIDENCE = ['source_node', 'required_target_kind', 'required_path', 'actual_targets']
LEGACY_PARITY_SOURCES = ['src/atdd/planner/validators/test_wmbt_has_smoke_acceptance.py']

_LEGACY_TARGET = ("src/atdd/planner/validators/test_wmbt_has_smoke_acceptance.py"
                  "::test_every_wmbt_has_smoke_acceptance")


def test_wmbt_has_smoke_acceptance_variant_contract() -> None:
    assert TEMPLATE in TEMPLATE_IDS, f"{TEMPLATE} not in coverage archetype"
    assert LEGACY_PARITY_SOURCES, "variant must record >=1 legacy parity source"
    assert set(FAILURE_EVIDENCE), "variant must declare failure evidence fields"


def test_clean_baseline_is_zero() -> None:
    """Real repo: every WMBT either has a SMOKE acceptance or is inline-suppressed."""
    root = _parity.repo_root()
    viols = _parity.conv_violations(root, _source_has_required_target,
                                    {"variant": VARIANT})
    assert viols == [], f"clean baseline must be 0, got {viols[:3]}"


def test_fault_injection_legacy_parity_both_catch() -> None:
    """Inject a WMBT whose only acceptance lacks the SMOKE token (and no inline
    suppression). The convention evaluator AND the legacy validator must BOTH
    catch it on the identical faulted tree."""
    root = _parity.repo_root()
    rel = "plan/validate_conventions/E997.yaml"
    content = (
        "urn: wmbt:validate-conventions:E997\n"
        "acceptances:\n"
        "  - identity:\n"
        "      urn: acc:validate-conventions:E997-UNIT-001-no-smoke-here\n"
    )

    assert not _parity.legacy_red(root, _LEGACY_TARGET), "legacy red on CLEAN tree"
    with _parity.inject_tempfile(root, rel, content):
        conv = _parity.conv_violations(root, _source_has_required_target,
                                       {"variant": VARIANT})
        legacy = _parity.legacy_red(root, _LEGACY_TARGET)
    caught = [v for v in conv if v["source_node"] == "wmbt:validate-conventions:E997"]
    assert caught, "convention evaluator must catch the no-SMOKE WMBT"
    assert caught[0]["required_target_kind"] == "acceptance:SMOKE"
    assert set(caught[0]).issubset(set(FAILURE_EVIDENCE))
    assert legacy is True, "legacy validator must ALSO catch (parity: both)"


def test_inline_suppression_is_respected() -> None:
    """A no-SMOKE WMBT carrying the inline suppression marker is NOT flagged —
    mirrors the legacy disposition gate so the clean baseline holds at 0."""
    root = _parity.repo_root()
    rel = "plan/validate_conventions/E996.yaml"
    content = (
        "urn: wmbt:validate-conventions:E996  "
        "# atdd:suppress(planner.wmbt.must-have-smoke-acceptance) UNTIL=2026-12-01\n"
        "acceptances:\n"
        "  - identity:\n"
        "      urn: acc:validate-conventions:E996-UNIT-001-no-smoke-here\n"
    )
    with _parity.inject_tempfile(root, rel, content):
        conv = _parity.conv_violations(root, _source_has_required_target,
                                       {"variant": VARIANT})
    assert not [v for v in conv if v["source_node"] == "wmbt:validate-conventions:E996"], \
        "inline-suppressed WMBT must not be flagged"
