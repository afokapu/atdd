# URN: component:govern-lifecycle:enforcement-substrate:suppression_filter:backend:domain
# Runtime: python
# Purpose: Split violations.jsonl into active / suppressed / stale-suppressions sets.

"""Suppression filter for the coach runtime (issue #520, spec §6.4 step 5).

After the dispatcher writes ``violations.jsonl``, the suppression filter
splits the record set into three outputs:

* **active** — violations that remain after absorbing suppress-and-clean
  violations whose inline markers match and have future ``UNTIL`` dates.
* **suppressed** — absorbed violations written to ``suppressed.jsonl``.
* **stale suppressions** — markers with past ``UNTIL`` dates written to
  ``stale-suppressions.jsonl``.

Repo rules (``repo.*``) are always ``strict`` per substrate v12 §2.
The filter routes by disposition — strict rules are never eligible for
suppression, so repo rules naturally stay active without special-casing.

The active set is the input to the risk scorer (#M5).
"""

from __future__ import annotations

import json
import os
import warnings
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import List, Optional, Sequence

from atdd.coach.utils.rule_binding import RuleNotInRegistryError, bind_rule
from atdd.coach.utils.suppression_scanner import (
    SuppressionMarker,
    find_stale_suppressions,
    find_suppressions,
)
from atdd.coach.validators._violation import Violation


@dataclass(frozen=True)
class SuppressionResult:
    """Tri-split of violations after suppression filtering.

    Attributes:
        active: Violations that remain after suppression. Input to the
            risk scorer (#M5).
        suppressed: Violations absorbed by matching suppress-and-clean
            markers. Written to ``suppressed.jsonl``.
        stale_suppressions: Markers whose ``UNTIL`` date is past. Written
            to ``stale-suppressions.jsonl``.
    """

    active: List[Violation] = field(default_factory=list)
    suppressed: List[Violation] = field(default_factory=list)
    stale_suppressions: List[SuppressionMarker] = field(default_factory=list)


def _resolve_location(marker: SuppressionMarker, worktree: Path) -> str:
    """Convert an absolute marker path to a relative location string."""
    try:
        rel = marker.file_path.relative_to(worktree)
    except ValueError:
        rel = marker.file_path
    return f"{rel}:{marker.line}"


def _read_marker_line(marker: SuppressionMarker) -> str:
    """Read the source line containing the marker text."""
    try:
        lines = marker.file_path.read_text(encoding="utf-8").splitlines()
        if 0 < marker.line <= len(lines):
            return lines[marker.line - 1].strip()
    except (OSError, UnicodeDecodeError):  # atdd:suppress(coder.logging.coach-silent-swallow)
        pass
    return ""


def _is_future_until(marker: SuppressionMarker, today: date) -> bool:
    """True when the marker's UNTIL is absent or in the future."""
    if marker.until is None:
        return True
    return marker.until >= today


def _append_jsonl(path: Path, record: dict) -> None:
    """Atomic append of a JSON line to *path*."""
    line = json.dumps(record, separators=(",", ":"), ensure_ascii=False) + "\n"
    data = line.encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        os.write(fd, data)
        os.fsync(fd)
    finally:
        os.close(fd)


def _get_disposition(rule_id: str) -> Optional[str]:
    """Look up disposition for a rule, returning None on unknown rules."""
    try:
        return bind_rule(rule_id).disposition
    except (RuleNotInRegistryError, Exception):  # atdd:suppress(coder.logging.coach-silent-swallow)
        return None


def apply_suppression(
    violations: List[Violation],
    worktree: Path,
    sha: str,
) -> SuppressionResult:
    """Filter violations into active / suppressed / stale-suppressions.

    Scans *worktree* for suppression markers, reconciles them against
    *violations* by disposition, and writes ``suppressed.jsonl`` and
    ``stale-suppressions.jsonl`` under
    ``<worktree>/.atdd/runtime/validations/<sha>/``.

    Args:
        violations: The violation list from ``violations.jsonl``.
        worktree: The agent worktree root (used for marker scanning).
        sha: The commit SHA (determines the output subdirectory).

    Returns:
        A ``SuppressionResult`` with the tri-split.
    """
    today = date.today()
    validation_dir = worktree / ".atdd" / "runtime" / "validations" / sha

    all_markers = find_suppressions([worktree])
    stale_markers = find_stale_suppressions([worktree], today=today)

    marker_index: dict[tuple[str, str], SuppressionMarker] = {}
    for m in all_markers:
        loc = _resolve_location(m, worktree)
        marker_index[(m.rule_id, loc)] = m

    active: List[Violation] = []
    suppressed: List[Violation] = []

    for v in violations:
        disposition = _get_disposition(v.rule_id)

        if disposition != "suppress-and-clean":
            active.append(v)
            continue

        key = (v.rule_id, v.location)
        marker = marker_index.get(key)

        if marker is not None and _is_future_until(marker, today):
            suppressed.append(v)
            continue

        active.append(v)

    suppressed_path = validation_dir / "suppressed.jsonl"
    for v in suppressed:
        key = (v.rule_id, v.location)
        marker = marker_index.get(key)
        marker_text = _read_marker_line(marker) if marker else ""
        until_str = marker.until.isoformat() if marker and marker.until else None
        record = {
            "rule_id": v.rule_id,
            "severity": v.severity,
            "location": v.location,
            "detail": v.detail,
            "marker_text": marker_text,
        }
        if until_str is not None:
            record["until"] = until_str
        if v.fix_hint_ref is not None:
            record["fix_hint_ref"] = v.fix_hint_ref
        _append_jsonl(suppressed_path, record)

    stale_path = validation_dir / "stale-suppressions.jsonl"
    for m in stale_markers:
        marker_text = _read_marker_line(m)
        until_str = m.until.isoformat() if m.until else None
        record = {
            "rule_id": m.rule_id,
            "location": _resolve_location(m, worktree),
            "marker_text": marker_text,
        }
        if until_str is not None:
            record["until"] = until_str
        _append_jsonl(stale_path, record)

    return SuppressionResult(
        active=active,
        suppressed=suppressed,
        stale_suppressions=stale_markers,
    )


__all__ = ["SuppressionResult", "apply_suppression"]
