# URN: component:define-plans:train-acceptances:TrainAcceptancesWellformed:backend:tests
# Runtime: python
# Purpose: Enforce planner.train.acceptances (#1548) — the node was documented but had no implementation and no validation block.

"""Every train-level acceptance is well-formed (``planner.train.acceptances``).

The convention node declared four constraints and bound NOTHING: it carried no
``implementation:`` and no ``validation:`` block, so a train acceptance could
violate all four and no validator would notice. It was an unbound doc node.

The four constraints, verbatim from the node:

* ``identity.urn`` matches the ``acc`` grammar (train-acceptance shape)
* ``identity.purpose`` populated (becomes ``RuleMetadata.description``)
* ``identity.phase`` populated (RED|GREEN|SMOKE|REFACTOR)
* EITHER ``harness.type`` OR (``signal.metric`` AND ``signal.threshold``)
  — the measurability invariant, spec §4.3

Plus the node's ``forbidden_fields``: no ``id:`` at the acceptance-block top
level (the rule-id derives mechanically from ``identity.urn`` per §3.3, so a
hand-written top-level ``id:`` is a second, silently-ignored identity).

Traversal comes from ``atdd.coach.utils.plan_paths`` — the shared utility layer
— so this validator cannot drift from the substrate walker about where trains
live. That drift is exactly what made train acceptances invisible (#1548).
"""

from __future__ import annotations

from pathlib import Path
from typing import List

import pytest
import yaml

from atdd.coach.utils.graph.urn import URNGrammar
from atdd.coach.utils.plan_paths import TRAINS_DIRNAME, iter_train_files
from atdd.coach.utils.repo import find_repo_root
from atdd.coach.utils.rule_binding import bind_rule
from atdd.coach.validators._violation import Violation


pytestmark = [pytest.mark.platform]

_RULE = bind_rule("planner.train.acceptances")

_PHASES = ("RED", "GREEN", "SMOKE", "REFACTOR")

FAILURE_EVIDENCE = ["train_file", "acceptance_urn", "constraint", "detail"]


def _violation(location: str, detail: str) -> Violation:
    return Violation(
        rule_id=_RULE.rule_id,
        severity=_RULE.severity,
        location=location,
        detail=detail,
        fix_hint_ref=_RULE.fix_hint_ref,
    )


def _check_block(block: dict, location: str) -> List[Violation]:
    """The node's four constraints + its forbidden field, on one block."""
    out: List[Violation] = []

    if not isinstance(block, dict):
        return [_violation(location, "acceptance entry is not a mapping")]

    identity = block.get("identity")
    if not isinstance(identity, dict):
        return [_violation(location, "acceptance is missing an identity block")]

    urn = identity.get("urn")
    if not isinstance(urn, str) or not urn:
        out.append(_violation(location, "identity.urn is missing"))
    elif not URNGrammar.validate_urn(urn, "acc"):
        out.append(_violation(
            location,
            f"identity.urn {urn!r} does not match the acc grammar; a train "
            f"acceptance is acc:<train-id>:<slug>, e.g. "
            f"acc:train:self-compliance:validate-lifecycle:idempotent-on-retry",
        ))

    if not (identity.get("purpose") or "").strip():
        out.append(_violation(location, f"{urn!r}: identity.purpose is empty"))

    phase = identity.get("phase")
    if phase not in _PHASES:
        out.append(_violation(
            location, f"{urn!r}: identity.phase {phase!r} is not one of {list(_PHASES)}"
        ))

    if not _is_measurable(block):
        out.append(_violation(
            location,
            f"{urn!r}: unenforceable — needs harness.type, or both signal.metric "
            f"and signal.threshold (measurability invariant §4.3)",
        ))

    if "id" in block:
        out.append(_violation(
            location,
            f"{urn!r}: `id:` at the acceptance-block top level is forbidden — the "
            f"rule-id derives from identity.urn (§3.3). Use identity.id for a "
            f"human-facing label.",
        ))

    return out


def _is_measurable(block: dict) -> bool:
    """EITHER harness.type OR (signal.metric AND signal.threshold) — §4.3.

    ``threshold`` is compared against ``None``, not truthiness: ``threshold: 0``
    is the common and meaningful case ("zero duplicate side effects") and must
    not read as absent.
    """
    harness = block.get("harness")
    if isinstance(harness, dict) and str(harness.get("type") or "").strip():
        return True

    signal = block.get("signal")
    if isinstance(signal, dict):
        has_metric = bool(str(signal.get("metric") or "").strip())
        has_threshold = signal.get("threshold") is not None
        return has_metric and has_threshold
    return False


def collect_violations(repo_root: Path | None = None) -> List[Violation]:
    """Walk plan/_trains/ and return every train-acceptance violation."""
    root = Path(repo_root).resolve() if repo_root is not None else find_repo_root()
    trains_dir = root / "plan" / TRAINS_DIRNAME

    violations: List[Violation] = []
    for train_file in sorted(iter_train_files(trains_dir)):
        try:
            doc = yaml.safe_load(train_file.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError):
            # Malformed train YAML is policed by the URN-graph/schema validators;
            # treating it as empty here keeps one broken file from masking the rest.
            continue
        if not isinstance(doc, dict):
            continue
        acceptances = doc.get("acceptances")
        if not isinstance(acceptances, list):
            continue

        try:
            rel = str(train_file.relative_to(root))
        except ValueError:
            rel = str(train_file)
        for idx, block in enumerate(acceptances):
            violations.extend(_check_block(block, f"{rel}:acceptances[{idx}]"))

    return violations


def test_train_acceptances_are_wellformed() -> None:
    """Every train acceptance in the real repo satisfies the node's constraints."""
    violations = collect_violations()
    assert violations == [], "\n".join(
        f"{v.location}: {v.detail}" for v in violations
    )
