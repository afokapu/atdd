"""Every convention node this program authors ships strict (#1400 enforce-merge-authority).

``disposition: advisory`` on a *new* rule is pure debt. Advisory exists to grandfather a
corpus that already violates a rule you cannot fix today — but the projection corpus
starts **empty**. There is nothing to grandfather. A new rule that ships advisory reports
a real violation and is ignored, and by the time anyone notices, the corpus it was meant
to protect has grown a backlog of exactly the fault it was written to catch (C004).

So the rule is: every convention node authored by train ``0006-state-projection`` ships
``disposition: strict``. ``advisory`` is permitted only when it is *paid for* — a written
precondition saying what must be true before it can go strict, and a named issue that
discharges it. An advisory with neither is refused.

A convention file opts into this rule by declaring its authoring train::

    authored_by_train: "0006-state-projection"

which is what makes the check honest rather than global: it governs the nodes this
program is responsible for, and says nothing about anyone else's.

Dependency discipline: stdlib + ``pyyaml`` only.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

import yaml

_log = logging.getLogger(__name__)

#: The train whose convention nodes this rule governs.
TRAIN_ID = "0006-state-projection"

#: The key a convention file uses to declare the train that authored it.
AUTHORED_BY_TRAIN = "authored_by_train"

STRICT = "strict"
ADVISORY = "advisory"

#: The two things an ``advisory`` node must carry to be admissible: what must become true
#: before it can go strict, and who is on the hook for making it true.
PRECONDITION_KEY = "advisory_precondition"
DISCHARGED_BY_KEY = "advisory_discharged_by"

#: Clause names a refusal carries.
CLAUSE_MISSING_DISPOSITION = "missing_disposition"
CLAUSE_UNKNOWN_DISPOSITION = "unknown_disposition"
CLAUSE_UNPAID_ADVISORY = "unpaid_advisory"


@dataclass(frozen=True)
class DispositionViolation:
    """One convention node whose disposition is not admissible."""

    rule_id: str
    clause: str
    detail: str
    source: Optional[str] = None

    def render(self) -> str:
        where = f"{self.source}: " if self.source else ""
        return f"{where}{self.rule_id} [{self.clause}] — {self.detail}"


@dataclass(frozen=True)
class DispositionReport:
    """The outcome of the disposition check over the nodes this program authors."""

    checked: int
    violations: List[DispositionViolation] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.violations

    def render(self) -> str:
        if self.ok:
            return (
                f"every convention node authored by train {TRAIN_ID} ships strict, or a "
                f"paid-for advisory ({self.checked} node(s))"
            )
        lines = [f"advisory disposition refused ({len(self.violations)}/{self.checked} node(s)):"]
        lines.extend(f"  - {violation.render()}" for violation in self.violations)
        return "\n".join(lines)


def check_node(node: Mapping[str, Any], *, source: Optional[str] = None) -> List[DispositionViolation]:
    """Every clause a single convention node fails (C004).

    Returns an empty list when the node ships strict, or ships a *paid-for* advisory.
    """
    rule_id = str(node.get("id") or node.get("name") or "<unnamed rule>")
    disposition = node.get("disposition")

    if disposition is None:
        return [DispositionViolation(
            rule_id, CLAUSE_MISSING_DISPOSITION,
            f"declares no disposition; a node authored by train {TRAIN_ID} must ship "
            f"'{STRICT}' explicitly",
            source,
        )]
    if disposition == STRICT:
        return []
    if disposition != ADVISORY:
        return [DispositionViolation(
            rule_id, CLAUSE_UNKNOWN_DISPOSITION,
            f"disposition {disposition!r} is neither {STRICT!r} nor {ADVISORY!r}",
            source,
        )]

    missing = [
        key for key in (PRECONDITION_KEY, DISCHARGED_BY_KEY)
        if not str(node.get(key) or "").strip()
    ]
    if missing:
        return [DispositionViolation(
            rule_id, CLAUSE_UNPAID_ADVISORY,
            f"ships advisory but declares no {sorted(missing)}; the projection corpus starts "
            "empty, so there is nothing to grandfather and advisory is pure debt",
            source,
        )]
    return []


def _rules(document: Mapping[str, Any]) -> List[Mapping[str, Any]]:
    rules = document.get("rules")
    return [rule for rule in rules if isinstance(rule, Mapping)] if isinstance(rules, list) else []


def check_convention(path: Path, *, train: str = TRAIN_ID) -> Optional[DispositionReport]:
    """Check one convention YAML, or return ``None`` when it is not this train's to govern."""
    document = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(document, Mapping):
        return None
    if str(document.get(AUTHORED_BY_TRAIN) or "") != train:
        return None
    rules = _rules(document)
    violations: List[DispositionViolation] = []
    for rule in rules:
        violations.extend(check_node(rule, source=Path(path).name))
    return DispositionReport(checked=len(rules), violations=violations)


def convention_files(root: Path) -> List[Path]:
    """Every convention YAML under ``root``, in a stable order."""
    return sorted(Path(root).glob("src/atdd/*/conventions/*.convention.yaml"))


def scan_conventions(root: Path, *, train: str = TRAIN_ID) -> DispositionReport:
    """Check every convention node the train authored, across the whole repository (C004).

    A repository carrying none of this train's convention nodes passes vacuously — which
    is correct, and is *why* the gate must be in place before the first one lands rather
    than after.
    """
    checked = 0
    violations: List[DispositionViolation] = []
    for path in convention_files(root):
        report = check_convention(path, train=train)
        if report is None:
            continue
        checked += report.checked
        violations.extend(report.violations)
    if violations:
        _log.warning(
            "advisory disposition refused on a new convention node",
            extra={"train": train, "violations": len(violations)},
        )
    return DispositionReport(checked=checked, violations=violations)


def summary(root: Path, *, train: str = TRAIN_ID) -> Dict[str, Any]:
    """A machine-readable rollup, for the CLI and for a caller that wants the numbers."""
    report = scan_conventions(root, train=train)
    return {
        "train": train,
        "checked": report.checked,
        "ok": report.ok,
        "violations": [
            {"rule_id": v.rule_id, "clause": v.clause, "source": v.source}
            for v in report.violations
        ],
    }
