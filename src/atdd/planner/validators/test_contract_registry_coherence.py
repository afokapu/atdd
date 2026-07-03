# Phase: RED
# Layer: backend.integration
"""planner.contract.registry-coherence validator (#1332, #1314 item D).

Cross-checks the authored contract registry (``contracts/_contracts.yaml``,
authored by ``create_contract`` — #1330) against the produce/consume graph
declared across ``plan/<wagon>/_<wagon>.yaml`` and enforces three coherence
invariants:

1. UNREGISTERED    — every non-null ``contract:`` URN on a produce/consume
   entry must strip to an identity present in the registry.
2. NULL-CROSS-WAGON — whenever an artifact NAME produced by one wagon is
   consumed by a *different* wagon (a cross-wagon edge), the producing entry
   must declare a non-null ``contract`` (kills the dangling-producer /
   ``contract: null`` class from the #250 audit).
3. UNCONSUMED      — every produce entry declaring a non-null ``contract``
   must be consumed by another wagon *or* be explicitly marked
   ``to: external``.

Disposition is ``advisory`` until the registry is authored (#1330) and the
corpus is repointed off ``contract: null``; the live scan reports the debt
without blocking. Detection is proven by the synthetic unit tests below.

Convention: src/atdd/planner/conventions/nodes/planner.contract.registry-coherence.convention.yaml
Rule:       planner.contract.registry-coherence
Run:        atdd validate planner
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Set

import pytest
import yaml

from atdd.coach.utils.disposition_gate import assert_disposition_satisfied
from atdd.coach.utils.repo import find_repo_root
from atdd.coach.utils.rule_binding import bind_rule
from atdd.coach.validators._violation import Violation

pytestmark = [pytest.mark.planner]

_RULE = bind_rule("planner.contract.registry-coherence")
_VALIDATOR_ID = "contract_registry_coherence"

REPO_ROOT = find_repo_root()
PLAN_DIR = REPO_ROOT / "plan"
REGISTRY_PATH = REPO_ROOT / "contracts" / "_contracts.yaml"

_CONTRACT_PREFIX = "contract:"


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------
def load_registry(registry_path: Path) -> Set[str]:
    """Return the set of registered contract IDENTITIES (``contract:`` stripped).

    The registry (``contracts/_contracts.yaml``, authored by #1330) is the SoT
    for identity -> {path, theme, producers, consumers}. Accepts either a list
    of entries under ``contracts:`` or a mapping keyed by identity. A missing or
    empty registry yields the empty set (nothing is registered yet).
    """
    if not registry_path.exists():
        return set()
    try:
        doc = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return set()
    contracts = doc.get("contracts") if isinstance(doc, dict) else None
    identities: Set[str] = set()
    if isinstance(contracts, list):
        for entry in contracts:
            if isinstance(entry, dict):
                ident = entry.get("identity") or entry.get("id") or entry.get("$id")
                if ident:
                    identities.add(_strip_prefix(str(ident)))
    elif isinstance(contracts, dict):
        for key, entry in contracts.items():
            ident = None
            if isinstance(entry, dict):
                ident = entry.get("identity") or entry.get("id") or entry.get("$id")
            identities.add(_strip_prefix(str(ident or key)))
    return identities


def load_manifests(plan_dir: Path) -> Dict[str, Dict[str, list]]:
    """wagon -> {'produce': [entry dicts], 'consume': [entry dicts]}.

    Unlike the name-only cycle validator, coherence needs the full entry dicts
    (``name``, ``contract``, ``to``, ``from``), so entries are kept intact.
    """
    out: Dict[str, Dict[str, list]] = {}
    for mf in sorted(plan_dir.glob("*/_*.yaml")):
        try:
            d = yaml.safe_load(mf.read_text()) or {}
        except Exception:
            continue
        wagon = d.get("wagon") or str(d.get("urn", "")).split(":")[-1]
        if not wagon:
            continue
        prod = [p for p in (d.get("produce") or []) if isinstance(p, dict) and p.get("name")]
        cons = [c for c in (d.get("consume") or []) if isinstance(c, dict) and c.get("name")]
        out[wagon] = {"produce": prod, "consume": cons}
    return out


def _strip_prefix(urn: str) -> str:
    return urn[len(_CONTRACT_PREFIX):] if urn.startswith(_CONTRACT_PREFIX) else urn


def _wagon_loc(wagon: str) -> str:
    w = wagon.replace("-", "_")
    return f"plan/{w}/_{w}.yaml:1"


# ---------------------------------------------------------------------------
# Coherence analysis (pure, unit-testable)
# ---------------------------------------------------------------------------
def find_incoherences(
    manifests: Dict[str, Dict[str, list]], registered: Set[str]
) -> List[Violation]:
    """Return one Violation per coherence breach across the three invariants."""
    violations: List[Violation] = []

    # producer NAME -> set of producing wagons (for cross-wagon detection)
    producers: Dict[str, Set[str]] = {}
    for wagon, io in manifests.items():
        for p in io["produce"]:
            producers.setdefault(p["name"], set()).add(wagon)

    # consumer NAME -> set of consuming wagons
    consumers: Dict[str, Set[str]] = {}
    for wagon, io in manifests.items():
        for c in io["consume"]:
            consumers.setdefault(c["name"], set()).add(wagon)

    for wagon in sorted(manifests):
        io = manifests[wagon]
        loc = _wagon_loc(wagon)

        # (1) UNREGISTERED — any non-null contract URN must resolve.
        for kind in ("produce", "consume"):
            for entry in io[kind]:
                contract = entry.get("contract")
                if contract and _strip_prefix(str(contract)) not in registered:
                    violations.append(
                        Violation(
                            rule_id=_RULE.rule_id,
                            severity=_RULE.severity,
                            location=loc,
                            detail=(
                                f"{kind} '{entry['name']}' references unregistered "
                                f"contract '{contract}' (not in contracts/_contracts.yaml)"
                            ),
                        )
                    )

        for p in io["produce"]:
            name = p["name"]
            contract = p.get("contract")
            is_external = str(p.get("to") or "external") == "external"
            cross_wagon_consumers = {w for w in consumers.get(name, set()) if w != wagon}

            # (2) NULL-CROSS-WAGON — a producer feeding another wagon needs a contract.
            if cross_wagon_consumers and not contract:
                violations.append(
                    Violation(
                        rule_id=_RULE.rule_id,
                        severity=_RULE.severity,
                        location=loc,
                        detail=(
                            f"produce '{name}' has contract null but is consumed "
                            f"cross-wagon by {sorted(cross_wagon_consumers)} "
                            f"(dangling producer)"
                        ),
                    )
                )

            # (3) UNCONSUMED — a produced contract needs a consumer or external mark.
            if contract and not cross_wagon_consumers and not is_external:
                violations.append(
                    Violation(
                        rule_id=_RULE.rule_id,
                        severity=_RULE.severity,
                        location=loc,
                        detail=(
                            f"produce '{name}' declares contract '{contract}' but has "
                            f"no consumer and is not marked to: external"
                        ),
                    )
                )

    return violations


def _scan_live() -> List[Violation]:
    return find_incoherences(load_manifests(PLAN_DIR), load_registry(REGISTRY_PATH))


# ---------------------------------------------------------------------------
# Live corpus gate (advisory until #1330 authors the registry)
# ---------------------------------------------------------------------------
def test_contract_registry_coherence() -> None:
    """Live corpus: producer/consumer edges must be coherent with the registry."""
    assert_disposition_satisfied(validator_id=_VALIDATOR_ID, violations=_scan_live())


# ---------------------------------------------------------------------------
# Synthetic detection guards (RED -> GREEN drivers, registry-independent)
# ---------------------------------------------------------------------------
def test_detects_unregistered_contract() -> None:
    """A contract URN absent from the registry MUST be flagged."""
    manifests = {
        "wagon-a": {
            "produce": [{"name": "x:art:a", "contract": "contract:x:art:a", "to": "external"}],
            "consume": [],
        },
    }
    v = find_incoherences(manifests, registered=set())  # nothing registered
    assert any("unregistered contract" in x.detail for x in v), v


def test_detects_null_contract_on_cross_wagon_edge() -> None:
    """A contract: null producer consumed by another wagon MUST be flagged."""
    manifests = {
        "wagon-a": {
            "produce": [{"name": "x:art:a", "contract": None, "to": "external"}],
            "consume": [],
        },
        "wagon-b": {"produce": [], "consume": [{"name": "x:art:a", "from": "wagon:wagon-a"}]},
    }
    v = find_incoherences(manifests, registered=set())
    assert any("dangling producer" in x.detail for x in v), v


def test_detects_produced_contract_without_consumer() -> None:
    """A produced contract with no consumer and not external MUST be flagged."""
    manifests = {
        "wagon-a": {
            "produce": [{"name": "x:art:a", "contract": "contract:x:art:a", "to": "internal"}],
            "consume": [],
        },
    }
    v = find_incoherences(manifests, registered={"x:art:a"})
    assert any("no consumer" in x.detail for x in v), v


def test_coherent_registry_and_graph_passes() -> None:
    """Registered contract, cross-wagon consumer present -> zero violations."""
    manifests = {
        "wagon-a": {
            "produce": [{"name": "x:art:a", "contract": "contract:x:art:a", "to": "internal"}],
            "consume": [],
        },
        "wagon-b": {
            "produce": [],
            "consume": [{"name": "x:art:a", "from": "wagon:wagon-a", "contract": "contract:x:art:a"}],
        },
    }
    v = find_incoherences(manifests, registered={"x:art:a"})
    assert v == [], v


def test_external_producer_without_consumer_passes() -> None:
    """A produced contract marked to: external needs no consumer."""
    manifests = {
        "wagon-a": {
            "produce": [{"name": "x:art:a", "contract": "contract:x:art:a", "to": "external"}],
            "consume": [],
        },
    }
    v = find_incoherences(manifests, registered={"x:art:a"})
    assert v == [], v
