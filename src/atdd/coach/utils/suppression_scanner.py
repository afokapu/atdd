# URN: component:govern-lifecycle:enforcement-substrate:suppression_scanner:backend:domain
# Runtime: python
# Purpose: Locate ``# atdd:suppress(<rule_id>) [UNTIL=<date>]`` markers and detect stale ones.

"""
Suppression-marker scanner (issue #395).

Walks ``.py``, ``.ts``, and ``.tsx`` files under a repo root looking for
inline pragmas of the form::

    # atdd:suppress(<RULE_ID>) [UNTIL=YYYY-MM-DD]      # python
    // atdd:suppress(<RULE_ID>) [UNTIL=YYYY-MM-DD]     # typescript / tsx

Match contract:
    Case-sensitive substring on a single line. The marker text after the
    comment leader is identical in every language; the leader itself
    (``#`` vs. ``//``) is matched by language. This preserves backward
    compatibility with the #357 silent-swallow scanner, which uses
    ``if SUPPRESSION_MARKER in line``.

Outputs:

* :func:`find_suppressions` — every marker, with its rule_id, ``UNTIL``
  date (or ``None``), file path, and line number.
* :func:`find_stale_suppressions` — markers whose ``UNTIL=`` date is in
  the past (per Decision 4: a missing ``UNTIL=`` is *not* stale).
* :func:`is_suppressed` — convenience predicate matching one offending
  line against one rule_id (the legacy contract used by #357).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable, List, Optional, Sequence


_logger = logging.getLogger(__name__)


# Files that may carry suppression markers.
_SCAN_EXTENSIONS = (".py", ".ts", ".tsx")

# Directories we never descend into (vendored / generated trees, virtualenvs).
_SKIP_DIR_NAMES = frozenset({
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    "site-packages",
    ".tox",
    ".git",
    "dist",
    "build",
    ".next",
    ".turbo",
})


# A marker may carry an optional `UNTIL=YYYY-MM-DD` segment; the rule_id
# token is everything between the parens (uppercase grammar but we capture
# permissively and validate the date separately).
_MARKER_PATTERN = re.compile(
    r"atdd:suppress\(([^)]+)\)(?:\s+UNTIL=(\d{4}-\d{2}-\d{2}))?",
)


@dataclass(frozen=True)
class SuppressionMarker:
    """One ``atdd:suppress(...)`` pragma occurrence."""

    rule_id: str
    file_path: Path
    line: int
    until: Optional[date] = None

    @property
    def is_stale(self) -> bool:
        """True when ``until`` is set and already past."""
        return self.until is not None and self.until < date.today()


def is_suppressed(line: str, rule_id: str) -> bool:
    """Legacy substring contract used by #357: marker present on the line.

    Matches both the bare and the ``UNTIL=``-stamped form.
    """
    return f"atdd:suppress({rule_id})" in line


def _iter_scan_files(root: Path) -> Iterable[Path]:
    """Yield every scannable file under *root*, skipping vendored trees."""
    if not root.is_dir():
        return
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix not in _SCAN_EXTENSIONS:
            continue
        if any(part in _SKIP_DIR_NAMES for part in path.parts):
            continue
        yield path


def _parse_until(raw: Optional[str]) -> Optional[date]:
    if raw is None:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        # Malformed dates are ignored — treated as `UNTIL` absent.
        _logger.debug(
            "suppression_scanner: ignoring malformed UNTIL=%r",
            raw,
            extra={"raw_until": raw},
        )
        return None


def _scan_file(path: Path) -> List[SuppressionMarker]:
    out: List[SuppressionMarker] = []
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return out
    for lineno, line in enumerate(text.splitlines(), start=1):
        for match in _MARKER_PATTERN.finditer(line):
            rid = match.group(1).strip()
            if not rid:
                continue
            out.append(SuppressionMarker(
                rule_id=rid,
                file_path=path,
                line=lineno,
                until=_parse_until(match.group(2)),
            ))
    return out


def find_suppressions(
    roots: Sequence[Path],
) -> List[SuppressionMarker]:
    """Return every suppression marker found under any *root*."""
    seen: List[SuppressionMarker] = []
    for root in roots:
        for f in _iter_scan_files(Path(root)):
            seen.extend(_scan_file(f))
    return seen


def find_stale_suppressions(
    roots: Sequence[Path],
    today: Optional[date] = None,
) -> List[SuppressionMarker]:
    """Return only the markers whose ``UNTIL=`` date is past *today*.

    *today* defaults to ``date.today()``. Per Decision 4, markers without
    an ``UNTIL=`` segment are NOT stale and are filtered out here.
    """
    threshold = today or date.today()
    out: List[SuppressionMarker] = []
    for marker in find_suppressions(roots):
        if marker.until is not None and marker.until < threshold:
            out.append(marker)
    return out


__all__ = [
    "SuppressionMarker",
    "find_stale_suppressions",
    "find_suppressions",
    "is_suppressed",
]
