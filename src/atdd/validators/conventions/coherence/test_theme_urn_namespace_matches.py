# URN: test:validate-conventions:coherence-variants:theme_urn_namespace_matches
# WMBT: wmbt:validate-conventions:E010
# Phase: GREEN
# Layer: integration
# Assertion: behavioral
"""Convention validator variant `coherence/theme_urn_namespace_matches` (#1206).

Instantiates the `coherence/resolved_fact_agreement` template against the composed convention
graph. Traversal execution lands incrementally on the _support graph engine;
this module fixes the variant's contract + legacy parity binding and is runnable
in parallel with legacy validators (imports no persona validator module).
"""
from __future__ import annotations

from pathlib import Path

from atdd.validators.conventions.coherence import _parity
from atdd.validators.conventions.coherence.archetype import (
    TEMPLATE_IDS,
    resolved_fact_agreement,
)
from atdd.validators.conventions.coherence.fixtures import (
    INVALID_FRAGMENTS,
    VALID_FRAGMENTS,
)

FAMILY = "coherence"
TEMPLATE = "resolved_fact_agreement"
VARIANT = "theme_urn_namespace_matches"
QUESTION = 'After references resolve, do the resolved facts agree with each other?'
SELECTOR = 'nodes declaring coherence checks or semantic comparison rules'
TRAVERSAL = 'source node -> resolved fact A; source node -> resolved fact B; compare A and B'
INVARIANT = 'facts satisfy comparison predicate'
AUTO_CAPTURE = 'partial; a new node is included only if it declares a known coherence predicate'
FAILURE_EVIDENCE = ['source_node', 'fact_a', 'fact_b', 'predicate', 'actual_values']
LEGACY_PARITY_SOURCES = ['src/atdd/planner/validators/test_theme_urn_namespace_matches.py']


def test_theme_urn_namespace_matches_variant_contract() -> None:
    assert TEMPLATE in TEMPLATE_IDS, f"{TEMPLATE} not in coherence archetype"
    assert LEGACY_PARITY_SOURCES, "variant must record >=1 legacy parity source"
    assert set(FAILURE_EVIDENCE), "variant must declare failure evidence fields"


# --- executable graph-question tests ---------------------------------------
#
# PARITY CLASSIFICATION (honest): legacy's repo-wide assertion
#   test_produced_urn_prefix_matches_theme  is marked xfail(strict=False) because
# the real repo carries ~43 genuine produced-URN theme-prefix divergences that are
# deferred to the #951 recompose co-land. An xfail target ALWAYS returns rc==0, so a
# subprocess "both catch an injected fault" differential is structurally impossible
# for this variant. Parity is therefore proven at the FUNCTION level against the
# legacy production check (`check_urn_namespace_matches`) on identical input — both
# the clean real repo (set-equal) and a faulted tmp tree (both catch). This is NOT a
# clean-baseline-zero variant: the convention evaluator faithfully reproduces the same
# 43 known #951-deferred divergences legacy's xfail acknowledges.


def test_real_repo_function_level_parity_with_legacy() -> None:
    """On the real composed graph the convention evaluator surfaces EXACTLY the
    produced-URN set legacy's check function surfaces (43 #951-deferred divergences)."""
    root = _parity.repo_root()
    conv = _parity.conv_violations(VARIANT, root)
    legacy = _parity.legacy_theme_urn_violations(root)
    conv_urns = {c["actual_values"]["produced_urn"] for c in conv}
    legacy_urns = {
        v.detail.split("produced URN '")[1].split("'")[0] for v in legacy
    }
    assert conv_urns == legacy_urns, (
        f"convention/legacy URN-divergence sets differ: "
        f"only-conv={conv_urns - legacy_urns}, only-legacy={legacy_urns - conv_urns}"
    )
    # The repo is genuinely NOT clean for this rule (deferred to #951); legacy
    # acknowledges this via xfail. Assert the divergence is present, not absent.
    assert conv_urns, "expected the known #951-deferred URN divergences to be present"


def test_fault_both_catch_function_level(tmp_path: Path) -> None:
    """On an identical faulted tmp tree, BOTH the convention evaluator and the
    legacy production check flag a coach wagon producing a commons:* URN."""
    from atdd.validators.conventions._support.graph_loader import load_composed_graph

    wdir = tmp_path / "plan" / "mediate_it"
    wdir.mkdir(parents=True)
    (wdir / "_mediate_it.yaml").write_text(
        'wagon: mediate-it\nurn: "wagon:mediate-it"\ntheme: coach\n'
        "produce:\n  - name: commons:decision:record\n",
        encoding="utf-8",
    )
    conv = resolved_fact_agreement(load_composed_graph(tmp_path), {"variant": VARIANT})
    legacy = _parity.legacy_theme_urn_violations(tmp_path)
    assert any(c["actual_values"]["produced_urn"] == "commons:decision:record" for c in conv), conv
    assert any(v.wagon == "mediate-it" for v in legacy), legacy


def test_invalid_fragment_is_caught() -> None:
    out = resolved_fact_agreement(INVALID_FRAGMENTS[VARIANT], {"variant": VARIANT})
    assert len(out) == 1 and out[0]["fact_b"] == "commons", out


def test_valid_fragment_is_clean() -> None:
    assert resolved_fact_agreement(VALID_FRAGMENTS[VARIANT], {"variant": VARIANT}) == []
