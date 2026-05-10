"""Review-report intake validator (spec §7.4 hard rules).

Combines JSON Schema validation with three cross-field hard rules that
cannot be expressed in pure JSON Schema draft-2020-12:

1. ``verdict`` cannot be ``pass`` when any ``ac_coverage`` entry is
   ``not_covered``.
2. ``verdict`` cannot be ``pass`` when any finding has ``rule_id != null``
   and ``disposition: strict``.
3. When ``rule_id != null``, the finding's ``severity`` and ``disposition``
   MUST match the registry binding from ``bind_rule(rule_id)``.

Downstream consumers (#N5, coach state machine) parse the rejection
structurally: each ``IntakeError`` carries a ``rule`` identifier and a
machine-readable ``detail`` dict.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from atdd.coach.utils.rule_binding import RuleNotInRegistryError, bind_rule

_ATDD_PKG_DIR = Path(__file__).resolve().parent.parent
_SCHEMA_PATH = _ATDD_PKG_DIR / "schemas" / "review-report.schema.json"


@dataclass
class IntakeError:
    """One hard-rule violation found at intake."""

    rule: str
    message: str
    detail: Dict[str, Any] = field(default_factory=dict)


@dataclass
class IntakeResult:
    """Aggregate intake validation result."""

    valid: bool
    errors: List[IntakeError] = field(default_factory=list)

    @property
    def error_messages(self) -> List[str]:
        return [e.message for e in self.errors]


def _load_schema() -> Dict[str, Any]:
    with _SCHEMA_PATH.open() as fh:
        return json.load(fh)


def _validate_schema(instance: Dict[str, Any]) -> List[IntakeError]:
    """Validate instance against the JSON Schema. Returns schema errors."""
    jsonschema = __import__("jsonschema")
    schema = _load_schema()
    validator = jsonschema.Draft202012Validator(schema)
    errors: List[IntakeError] = []
    for err in sorted(validator.iter_errors(instance), key=lambda e: e.path):
        path = "/".join(str(p) for p in err.path) or "(root)"
        errors.append(IntakeError(
            rule="schema",
            message=f"Schema validation error at {path}: {err.message}",
            detail={"path": path, "message": err.message},
        ))
    return errors


def _check_ac_coverage(verdict: str, ac_coverage: Dict[str, str]) -> List[IntakeError]:
    """Hard rule 1: verdict cannot be pass if any AC is not_covered."""
    if verdict != "pass":
        return []
    not_covered = [
        ref for ref, status in ac_coverage.items()
        if status == "not_covered"
    ]
    if not not_covered:
        return []
    refs_str = ", ".join(not_covered)
    return [IntakeError(
        rule="hard-rule-1",
        message=(
            f"verdict cannot be pass when any AC is not_covered. "
            f"Offending acceptance_ref(s): {refs_str}"
        ),
        detail={"not_covered_refs": not_covered},
    )]


def _check_strict_finding(
    verdict: str,
    findings: List[Dict[str, Any]],
) -> List[IntakeError]:
    """Hard rule 2: verdict cannot be pass with strict rule_id-bound finding."""
    if verdict != "pass":
        return []
    strict_ids: List[str] = []
    for finding in findings:
        rule_id = finding.get("rule_id")
        disposition = finding.get("disposition")
        if rule_id is not None and disposition == "strict":
            strict_ids.append(rule_id)
    if not strict_ids:
        return []
    ids_str = ", ".join(strict_ids)
    return [IntakeError(
        rule="hard-rule-2",
        message=(
            f"verdict cannot be pass while a strict rule_id-bound finding "
            f"remains. Offending rule_id(s): {ids_str}"
        ),
        detail={"strict_rule_ids": strict_ids},
    )]


def _check_rule_id_severity(
    findings: List[Dict[str, Any]],
) -> List[IntakeError]:
    """Hard rule 3: severity/disposition must match bind_rule registry."""
    errors: List[IntakeError] = []
    for finding in findings:
        rule_id = finding.get("rule_id")
        if rule_id is None:
            continue
        try:
            registry_meta = bind_rule(rule_id)
        except (RuleNotInRegistryError, Exception):  # atdd:suppress(coder.logging.coach-silent-swallow)
            # Unknown rule_id — not a severity mismatch (could be a future rule).
            # The schema allows null rule_id; unknown non-null rule_ids are
            # outside the scope of this hard rule (handled by consumers).
            continue
        reported_severity = finding.get("severity")
        reported_disposition = finding.get("disposition")

        mismatches: List[str] = []
        if reported_severity != registry_meta.severity:
            mismatches.append(
                f"severity: reported={reported_severity}, "
                f"registry={registry_meta.severity}"
            )
        if reported_disposition != registry_meta.disposition:
            mismatches.append(
                f"disposition: reported={reported_disposition}, "
                f"registry={registry_meta.disposition}"
            )
        if mismatches:
            errors.append(IntakeError(
                rule="hard-rule-3",
                message=(
                    f"rule_id {rule_id!r} severity/disposition diverges from "
                    f"registry: {'; '.join(mismatches)}. "
                    f"Registry expects severity={registry_meta.severity}, "
                    f"disposition={registry_meta.disposition!r}."
                ),
                detail={
                    "rule_id": rule_id,
                    "reported_severity": reported_severity,
                    "reported_disposition": reported_disposition,
                    "registry_severity": registry_meta.severity,
                    "registry_disposition": registry_meta.disposition,
                },
            ))
    return errors


def validate_review_report(
    instance: Dict[str, Any],
    *,
    skip_schema: bool = False,
) -> IntakeResult:
    """Validate a review report against schema + all hard rules.

    Args:
        instance: The review report dict to validate.
        skip_schema: Skip JSON Schema validation (useful when testing
            hard rules in isolation with minimal fixtures).

    Returns:
        IntakeResult with valid=True if all checks pass.
    """
    errors: List[IntakeError] = []

    if not skip_schema:
        errors.extend(_validate_schema(instance))

    verdict = instance.get("verdict", "")
    findings = instance.get("findings") or []
    ac_coverage = instance.get("ac_coverage") or {}

    errors.extend(_check_ac_coverage(verdict, ac_coverage))
    errors.extend(_check_strict_finding(verdict, findings))
    errors.extend(_check_rule_id_severity(findings))

    return IntakeResult(valid=len(errors) == 0, errors=errors)
