# URN: component:govern-lifecycle:enforcement-substrate:test_hermetic_integration_contract:backend:application
# Runtime: python
# Purpose: Issue #690 — a hermetic_integration acceptance with permitted_fakes must declare its fidelity contract and use only controlled boundary_kinds.

"""Hermetic-integration fidelity-contract conformance validator (issue #690).

Binds ``tester.acceptance-violation.hermetic-fake-must-declare-contract``.

A ``hermetic_integration`` acceptance that substitutes any fake (cassette,
recorded LLM response, in-memory backend) must declare the ``hermetic:`` block
honestly: which boundaries it exercises, what each fake faithfully reproduces,
what it does NOT prove (``known_gaps``), and whether a paired live smoke is
required. The declaration IS the contract.

The rule fires ONLY when an acceptance EXPLICITLY declares
``execution_kind: hermetic_integration`` AND ``hermetic.permitted_fakes`` is
non-empty. Acceptances without ``execution_kind`` are never retroactively
flagged (Decision #11).

``evaluate_hermetic_fidelity_declaration`` is a pure evaluator: it accepts a
sequence of ``(path, acceptance_dict)`` pairs and returns a list of
``Violation`` records, so callers (and RED fixtures) can inspect the result
directly without pytest.fail interception.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import pytest

from atdd.coach.utils.repo import find_repo_root
from atdd.coach.utils.rule_binding import bind_rule
from atdd.coach.validators._violation import Violation
from atdd.tester.validators._acceptance_walker import (
    acceptance_urn,
    assert_substrate_strict,
    iter_repo_acceptances,
)


pytestmark = [pytest.mark.platform]


_RULE = bind_rule("tester.acceptance-violation.hermetic-fake-must-declare-contract")
_VALIDATOR_ID = (
    "test_hermetic_integration_contract::test_no_undeclared_hermetic_fakes"
)

# Controlled boundary vocabulary — mirrors acceptance.convention.yaml::boundary_kinds.
BOUNDARY_KINDS = frozenset(
    {
        "argv",
        "subprocess",
        "filesystem",
        "git",
        "http_wire",
        "llm_wire",
        "cmux_rpc",
        "env_config",
        "db_wire",
        "event_wire",
    }
)


def evaluate_hermetic_fidelity_declaration(
    items: Sequence[Tuple[Path, Dict[str, Any]]],
) -> List[Violation]:
    """Return fidelity-contract violations for the given acceptance blocks.

    Pure function. ``items`` is a sequence of ``(path, acceptance_dict)``
    pairs. A Violation is emitted for an acceptance that declares
    ``execution_kind: hermetic_integration`` with a non-empty
    ``hermetic.permitted_fakes`` list and either:

      - omits a required ``hermetic:`` field
        (``exercised_boundaries`` / ``fake_contract_fidelity`` /
        ``live_smoke_required``), or
      - lists a ``fake_contract_fidelity`` entry without ``known_gaps``, or
      - declares an ``exercised_boundaries`` value outside ``BOUNDARY_KINDS``.
    """
    violations: List[Violation] = []

    for path, acc in items:
        if not isinstance(acc, dict):
            continue
        if acc.get("execution_kind") != "hermetic_integration":
            continue

        hermetic = acc.get("hermetic")
        if not isinstance(hermetic, dict):
            hermetic = {}

        permitted_fakes = hermetic.get("permitted_fakes")
        # Rule applies ONLY when fakes are actually permitted (Decision #11).
        if not permitted_fakes:
            continue

        urn = acceptance_urn(acc) or "<no-urn>"
        location = str(path)

        def _flag(detail: str) -> None:
            violations.append(
                Violation(
                    rule_id=_RULE.rule_id,
                    severity=_RULE.severity,
                    location=location,
                    detail=detail,
                    fix_hint_ref=_RULE.fix_hint_ref,
                )
            )

        # 1. Required hermetic: fields.
        if hermetic.get("exercised_boundaries") is None:
            _flag(
                f"hermetic acceptance {urn!r} permits fakes but omits required "
                f"field hermetic.exercised_boundaries"
            )
        fidelity = hermetic.get("fake_contract_fidelity")
        if not fidelity:
            _flag(
                f"hermetic acceptance {urn!r} permits fakes but omits required "
                f"field hermetic.fake_contract_fidelity"
            )
        if "live_smoke_required" not in hermetic:
            _flag(
                f"hermetic acceptance {urn!r} permits fakes but omits required "
                f"field hermetic.live_smoke_required"
            )

        # 2. Every fake_contract_fidelity entry must declare known_gaps.
        if isinstance(fidelity, list):
            for entry in fidelity:
                if isinstance(entry, dict) and not entry.get("known_gaps"):
                    name = entry.get("name", "<unnamed>")
                    _flag(
                        f"hermetic acceptance {urn!r} fake_contract_fidelity "
                        f"entry {name!r} omits required known_gaps"
                    )

        # 3. exercised_boundaries values must be in the controlled vocabulary.
        boundaries = hermetic.get("exercised_boundaries")
        if isinstance(boundaries, list):
            for boundary in boundaries:
                if boundary not in BOUNDARY_KINDS:
                    _flag(
                        f"hermetic acceptance {urn!r} declares unknown "
                        f"exercised_boundary {boundary!r}; permitted boundary_kinds: "
                        f"{sorted(BOUNDARY_KINDS)}"
                    )

    return violations


def collect_violations(repo_root: Optional[Path] = None) -> List[Violation]:
    """Walk plan/ and return hermetic fidelity-contract violations."""
    root = Path(repo_root).resolve() if repo_root is not None else find_repo_root()
    items = [(raw.file, raw.body) for raw in iter_repo_acceptances(root)]
    return evaluate_hermetic_fidelity_declaration(items)


def test_no_undeclared_hermetic_fakes() -> None:
    """Every fake-backed hermetic acceptance under plan/ declares its contract."""
    assert_substrate_strict(_VALIDATOR_ID, collect_violations())


__all__ = [
    "BOUNDARY_KINDS",
    "collect_violations",
    "evaluate_hermetic_fidelity_declaration",
    "test_no_undeclared_hermetic_fakes",
]
