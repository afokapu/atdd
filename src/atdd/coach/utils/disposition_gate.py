# URN: component:govern-lifecycle:enforcement-substrate:disposition_gate:backend:domain
# Runtime: python
# Purpose: Decide pass/fail per validator from per-rule disposition + Violation list.

"""
Disposition-driven gate (issue #395).

Replaces ``RatchetBaseline.assert_no_regression(...)``. Given:

* a list of structured ``Violation`` records for one validator,
* the convention registry built from ``*.convention.yaml`` files,

decides pass/fail per the rule's ``disposition``:

* ``strict``              — any violation fails CI immediately.
* ``suppress-and-clean``  — violations whose offending line carries an
  inline ``# atdd:suppress(<rule_id>)`` marker are absorbed; everything
  else fails CI with a per-site punch list.
* ``advisory``            — violations log a warning and pass.

Failures print rule_id + severity + disposition + ``file:line`` + the
detail string + a one-line suggested action so a reviewer doesn't have to
read the validator source to understand the failure.

A rule_id with no registry entry is treated as ``strict`` (defensive
default — unregistered rules should be caught by the
``rule_id_registry_coherence`` validator before reaching this point).
"""

from __future__ import annotations

import logging
import warnings
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import pytest

from atdd.coach.utils.repo import find_repo_root
from atdd.coach.utils.rule_id_registry import RuleMetadata, build_registry
from atdd.coach.utils.suppression_scanner import is_suppressed


_logger = logging.getLogger(__name__)


_DEFAULT_DISPOSITION = "strict"
_LEGAL_DISPOSITIONS = frozenset({"strict", "suppress-and-clean", "advisory"})


def _looks_like_violation(obj: Any) -> bool:
    """Duck-typed check: structured ``Violation`` carries rule_id+severity+location."""
    return (
        hasattr(obj, "rule_id")
        and hasattr(obj, "severity")
        and hasattr(obj, "location")
    )


def _split_location(location: str) -> tuple[str, Optional[int]]:
    """Parse ``"path:line"`` (or ``"path:line:col"``) into ``(path, line)``.

    Returns ``(location, None)`` when the location string lacks a numeric
    line component.
    """
    # Handle path:line and path:line:col by trying each tail position.
    parts = location.split(":")
    if len(parts) >= 2:
        # path:line:col → line is parts[-2]; path:line → line is parts[-1]
        for candidate_idx in (-2, -1):
            try:
                lineno = int(parts[candidate_idx])
            except (ValueError, IndexError):
                continue
            path = ":".join(parts[: candidate_idx if candidate_idx == -2 else -1])
            return path, lineno
    return location, None


def _read_line(repo_root: Path, rel_path: str, lineno: int) -> Optional[str]:
    """Best-effort read of one line for marker matching."""
    p = (repo_root / rel_path) if not Path(rel_path).is_absolute() else Path(rel_path)
    try:
        with open(p, encoding="utf-8") as fh:
            for idx, line in enumerate(fh, start=1):
                if idx == lineno:
                    return line
    except (OSError, UnicodeDecodeError):  # atdd:suppress(coder.logging.coach-silent-swallow)
        return None
    return None


def _format_violation(v: Any, disposition: str) -> str:
    return (
        f"  [{v.rule_id} sev={v.severity} disposition={disposition}] "
        f"{v.location}: {v.detail}"
    )


def _suggest_marker_for(rule_id: str) -> str:
    return (
        f"      Either fix the violation, or add an inline marker on the "
        f"offending line:\n"
        f"        # atdd:suppress({rule_id}) UNTIL=<YYYY-MM-DD>"
    )


def assert_disposition_satisfied(
    validator_id: str,
    violations: Sequence[Any],
    registry: Optional[Dict[str, RuleMetadata]] = None,
    repo_root: Optional[Path] = None,
) -> None:
    """Pass/fail the calling test based on per-rule disposition.

    Args:
        validator_id: Stable name of the validator (used in failure
            messages and warnings — replaces RatchetBaseline's
            ``validator_id`` parameter).
        violations: Sequence of structured ``Violation`` records. Bare
            strings or dicts are accepted for back-compat but downgrade
            the gate to strict-by-default (no rule_id ⇒ no disposition
            ⇒ fail on any non-empty list).
        registry: Optional pre-built registry. Defaults to
            ``build_registry()`` which walks every ``*.convention.yaml``.
        repo_root: Optional override for resolving violation locations
            (``path:line``) when matching suppression markers. Defaults
            to ``find_repo_root()``.

    Behavior:
        - Empty ``violations`` → pass silently.
        - Group by ``rule_id``; look up ``disposition`` per rule.
        - ``strict``: any violation → ``pytest.fail`` with full punch list.
        - ``suppress-and-clean``: split into suppressed vs unsuppressed
          via inline ``# atdd:suppress(<rule_id>)`` marker on the
          offending line. Unsuppressed → ``pytest.fail``; suppressed →
          silent pass (deadline auditing is the
          ``test_no_stale_suppressions.py`` validator's job).
        - ``advisory``: ``warnings.warn`` (UserWarning) and pass.
        - Unknown ``rule_id`` (not in registry) → treated as ``strict``.
        - Bare-string / dict ``violations`` (legacy callers): treated as
          a single ``strict`` bucket because there is no rule_id to look
          up. Empty → pass; non-empty → fail.
    """
    if not violations:
        return

    registry = registry if registry is not None else build_registry()
    root = repo_root if repo_root is not None else find_repo_root()

    # Bucket structured Violations by rule_id; collect opaque entries
    # separately under a sentinel bucket.
    structured: Dict[str, List[Any]] = defaultdict(list)
    opaque: List[Any] = []
    for v in violations:
        if _looks_like_violation(v):
            structured[v.rule_id].append(v)
        else:
            opaque.append(v)

    failures: List[str] = []
    advisory_blocks: List[str] = []

    for rule_id, vs in structured.items():
        meta = registry.get(rule_id)
        disposition = (meta.disposition if meta and meta.disposition else _DEFAULT_DISPOSITION)
        if disposition not in _LEGAL_DISPOSITIONS:
            disposition = _DEFAULT_DISPOSITION

        if disposition == "advisory":
            advisory_blocks.append(
                _format_advisory_block(validator_id, rule_id, vs, registry)
            )
            continue

        if disposition == "strict":
            failures.append(_format_failure_block(
                validator_id=validator_id,
                rule_id=rule_id,
                disposition=disposition,
                violations=vs,
                suppressed_count=0,
                registry=registry,
            ))
            continue

        # suppress-and-clean
        suppressed: List[Any] = []
        unsuppressed: List[Any] = []
        for v in vs:
            rel_path, lineno = _split_location(v.location)
            line_text: Optional[str] = None
            if lineno is not None:
                line_text = _read_line(root, rel_path, lineno)
            if line_text is not None and is_suppressed(line_text, rule_id):
                suppressed.append(v)
            else:
                unsuppressed.append(v)
        if unsuppressed:
            failures.append(_format_failure_block(
                validator_id=validator_id,
                rule_id=rule_id,
                disposition=disposition,
                violations=unsuppressed,
                suppressed_count=len(suppressed),
                registry=registry,
            ))

    # Opaque violations: no rule_id ⇒ default-strict.
    if opaque:
        failures.append(_format_opaque_block(validator_id, opaque))

    for block in advisory_blocks:
        warnings.warn(block, UserWarning, stacklevel=2)

    if failures:
        header = (
            f"\n[disposition gate] {validator_id}: "
            f"{sum(_count_block_violations(b) for b in failures)} unsuppressed violation(s)\n"
        )
        pytest.fail(header + "\n".join(failures))


def _count_block_violations(block: str) -> int:
    # Each violation is one indented "  [..." line; cheap line count
    return sum(1 for ln in block.splitlines() if ln.lstrip().startswith("["))


def _format_failure_block(
    validator_id: str,
    rule_id: str,
    disposition: str,
    violations: Sequence[Any],
    suppressed_count: int,
    registry: Optional[Dict[str, RuleMetadata]] = None,
) -> str:
    lines = [
        f"\n  rule_id={rule_id} disposition={disposition} "
        f"validator={validator_id} ({len(violations)} unsuppressed"
        + (f", {suppressed_count} suppressed" if suppressed_count else "")
        + "):",
    ]
    meta = registry.get(rule_id) if registry else None
    if meta and meta.description:
        lines.append(f"    description: {meta.description.splitlines()[0]}")
    if meta and meta.fix_hint:
        lines.append(f"    fix_hint:    {meta.fix_hint.splitlines()[0]}")
    for v in violations:
        lines.append(_format_violation(v, disposition))
    if disposition == "suppress-and-clean":
        lines.append("")
        lines.append(_suggest_marker_for(rule_id))
    return "\n".join(lines)


def _format_advisory_block(
    validator_id: str,
    rule_id: str,
    violations: Sequence[Any],
    registry: Optional[Dict[str, RuleMetadata]] = None,
) -> str:
    lines = [
        f"[advisory] {validator_id} {rule_id}: {len(violations)} violation(s)"
    ]
    meta = registry.get(rule_id) if registry else None
    if meta and meta.description:
        lines.append(f"    description: {meta.description.splitlines()[0]}")
    if meta and meta.fix_hint:
        lines.append(f"    fix_hint:    {meta.fix_hint.splitlines()[0]}")
    for v in violations:
        lines.append(_format_violation(v, "advisory"))
    return "\n".join(lines)


def _format_opaque_block(validator_id: str, opaque: Sequence[Any]) -> str:
    lines = [
        f"\n  validator={validator_id}: "
        f"{len(opaque)} legacy (no rule_id) violation(s) — strict by default:"
    ]
    for v in opaque:
        lines.append(f"    {v}")
    return "\n".join(lines)


__all__ = ["assert_disposition_satisfied"]
