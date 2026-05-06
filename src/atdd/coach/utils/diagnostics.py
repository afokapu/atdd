"""Structured diagnostics helpers (issue #449).

Provides ``fail_with_diagnostic()`` — a drop-in replacement for
``pytest.fail()`` that records a structured ``Finding`` (with optional
per-violation ``Item`` rows) into a module-level pending-findings map
keyed by the active pytest nodeid, then raises ``pytest.fail(message)``.

The diagnostics plugin (``atdd.coach.plugins.diagnostics``):
  * Tracks the active nodeid in ``pytest_runtest_setup`` /
    ``pytest_runtest_teardown`` (writing into ``set_active_nodeid``).
  * Reads pending findings off ``get_pending_findings()`` in
    ``pytest_runtest_logreport`` and attaches them to the report.
  * Writes everything to ``.atdd/diagnostics/validation/<phase>.yaml``
    at session finish.

Schema is frozen as ``schema_version: 1`` — see
``docs/specs/atdd-diagnostics-spec-v1.md``.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Sequence

import pytest

# Closed enum — keep in sync with the spec doc.
LEGAL_CATEGORIES = frozenset({
    "naming",
    "missing-file",
    "contract",
    "boundary",
    "hygiene",
    "quality",
    "train",
    "workflow",
    "convention",
    "unmigrated",
})

LEGAL_SEVERITIES = frozenset({"error", "warning"})


@dataclass
class Item:
    """One concrete violation within a finding."""

    file: Optional[str] = None
    line: Optional[int] = None
    column: Optional[int] = None
    symbol: Optional[str] = None
    expected: Optional[str] = None
    found: Optional[str] = None
    fix: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ConventionRef:
    """Pointer to a convention rule (file + anchor) backing a finding."""

    file: Optional[str] = None
    anchor: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Finding:
    """One failed validator's structured failure record."""

    validator_id: str
    validator_path: Optional[str]
    category: str
    severity: str
    summary: str
    raw_message: str
    items: List[Item] = field(default_factory=list)
    convention_ref: Optional[ConventionRef] = None

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "validator_id": self.validator_id,
            "validator_path": self.validator_path,
            "category": self.category,
            "severity": self.severity,
        }
        if self.convention_ref is not None:
            d["convention_ref"] = self.convention_ref.to_dict()
        d["summary"] = self.summary
        d["items"] = [i.to_dict() for i in self.items]
        d["raw_message"] = self.raw_message
        return d


# ---------------------------------------------------------------------------
# Active-item bookkeeping (used by the diagnostics plugin).
# ---------------------------------------------------------------------------
# A module-level "currently running test" pointer. Pytest is single-threaded
# per worker process (xdist runs one item at a time per worker), so the
# pointer is safe without locking. The plugin sets it in
# ``pytest_runtest_setup`` and clears it in ``pytest_runtest_teardown``.

_ACTIVE_NODEID: Optional[str] = None
_PENDING_FINDINGS: Dict[str, List[Finding]] = {}


def set_active_nodeid(nodeid: Optional[str]) -> None:
    """Plugin hook — record the nodeid of the currently-running pytest item.

    Called from the diagnostics plugin's ``pytest_runtest_setup`` /
    ``pytest_runtest_teardown`` hooks. Outside a pytest run the value
    stays ``None`` and ``fail_with_diagnostic`` becomes a thin wrapper
    around ``pytest.fail`` (no recording side-effect).
    """
    global _ACTIVE_NODEID
    _ACTIVE_NODEID = nodeid


def get_pending_findings(nodeid: str) -> List[Finding]:
    """Plugin hook — pop the pending findings recorded against *nodeid*."""
    return _PENDING_FINDINGS.pop(nodeid, [])


def clear_pending_findings() -> None:
    """Test/plugin hook — drop all pending findings (e.g. on session start)."""
    _PENDING_FINDINGS.clear()


def _coerce_items(items: Sequence[Any]) -> List[Item]:
    """Accept ``Item`` instances OR plain dicts and return ``Item`` rows."""
    out: List[Item] = []
    for raw in items:
        if isinstance(raw, Item):
            out.append(raw)
            continue
        if isinstance(raw, dict):
            out.append(Item(**{k: v for k, v in raw.items() if k in Item.__dataclass_fields__}))
            continue
        out.append(Item(extra={"value": repr(raw)}))
    return out


def fail_with_diagnostic(
    message: str,
    *,
    category: str,
    items: Sequence[Any] = (),
    convention_ref: Optional[ConventionRef] = None,
    severity: str = "error",
    summary: Optional[str] = None,
) -> None:
    """Record a structured diagnostic finding then call ``pytest.fail()``.

    Behavior:
      * Always calls ``pytest.fail(message)`` after recording the finding —
        callers that have not migrated still see the same ``longrepr`` text
        they always have.
      * Empty ``items`` is valid — the validator is reporting a structural
        failure ("file missing") rather than per-item violations.
      * Outside a pytest run (helper called from a script), the recording
        step is a silent no-op and ``pytest.fail`` still raises.

    Args:
        message: Verbose message — passed verbatim to ``pytest.fail`` and
            stored as ``raw_message`` on the finding.
        category: Closed-enum classification (see ``LEGAL_CATEGORIES``).
        items: Optional per-violation ``Item`` rows (or dicts).
        convention_ref: Optional ``ConventionRef`` backing the failure.
        severity: ``"error"`` (default) or ``"warning"``.
        summary: Short one-line summary; defaults to first non-empty
            line of ``message``.
    """
    nodeid = _ACTIVE_NODEID
    finding = Finding(
        validator_id=_validator_id_from_nodeid(nodeid),
        validator_path=_validator_path_from_nodeid(nodeid),
        category=category,
        severity=severity if severity in LEGAL_SEVERITIES else "error",
        summary=summary or _first_line(message),
        raw_message=message,
        items=_coerce_items(items),
        convention_ref=convention_ref,
    )

    if nodeid is not None:
        _PENDING_FINDINGS.setdefault(nodeid, []).append(finding)

    pytest.fail(message)


def _first_line(text: str) -> str:
    """Return the first non-empty line of *text*, stripped."""
    for line in text.splitlines():
        line = line.strip()
        if line:
            return line
    return text.strip()


def _validator_id_from_nodeid(nodeid: Optional[str]) -> str:
    if not nodeid:
        return "<unknown>"
    if "::" in nodeid:
        return nodeid.rsplit("::", 1)[-1]
    return nodeid


def _validator_path_from_nodeid(nodeid: Optional[str]) -> Optional[str]:
    if not nodeid:
        return None
    if "::" in nodeid:
        return nodeid.split("::", 1)[0]
    return nodeid


__all__ = [
    "ConventionRef",
    "Finding",
    "Item",
    "LEGAL_CATEGORIES",
    "LEGAL_SEVERITIES",
    "clear_pending_findings",
    "fail_with_diagnostic",
    "get_pending_findings",
    "set_active_nodeid",
]
