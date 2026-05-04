# URN: component:govern-lifecycle:enforcement-substrate:rule_id_emission_extractor:backend:domain
# Runtime: python
# Purpose: Regex-based extractor for rule_id emissions in production validator + command source.

"""
Rule-ID emission extractor (issue #387, Phase 2 helper).

Extracts every string-literal rule_id emission from a Python source file.
Decision #1 of #387 fixes the regex set:

  Pattern A — `Violation\\(\\s*rule_id\\s*=\\s*"([A-Z][A-Z0-9-]+)"`
              Matches the canonical Violation kwarg form.
  Pattern B — `\\b([A-Z][A-Z0-9_]*)\\s*=\\s*"([A-Z][A-Z0-9]*(?:-[A-Z0-9]+){2,})"`
              Matches any all-caps identifier whose VALUE conforms to the
              rule_id grammar — catches RULE_ID_*, *_RULE_ID, AND constants
              whose names contain neither (RULE_EMPTY_RENDER, XSS_RULE_ID,
              RULE_DYNAMIC_TRAIN_ID, RULE_ALLOWLIST_MIGRATION, …).
  Pattern C — catch-all for any keyword-arg string literal that names
              ``rule_id`` (e.g. babysit's auto-approval builder); ensures a
              non-Violation constructor still gets scanned.

Out-of-scope for v1: dynamic emissions where the rhs is an attribute or
subscript reference instead of a string literal (e.g. babysit's per-rule
loop where the rhs reads from a parsed config). These require AST +
control-flow analysis and are deferred until v1's false-negative rate
forces the upgrade.

Decision #4 / Success Criteria file exclusions are applied in
``iter_scan_files``:
  - ``**/tests/**`` (pytest unit tests of validators)
  - ``**/fixtures/**`` (placeholder rule_ids in fixtures)

Validator files named ``test_*.py`` are NOT excluded — those files ARE the
production validators (pytest discovers validators by filename). The scan
roots (``validators/``, ``coach/commands/``) bound the surface; stragglers
like ``coder/baselines/test_ratchet.py`` are out of reach because they
live outside the scan roots.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Sequence


_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Decision #1 regex set
# ---------------------------------------------------------------------------
# Match either a legacy flat-grammar id (uppercase, hyphen-separated) OR a
# canonical namespaced id (lowercase, dot-separated). Both shapes resolve via
# the registry's alias index, so the extractor needs to surface both.
_LEGACY_ID = r"[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+"
_NAMESPACED_ID = (
    r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*"
    r"\.[a-z][a-z0-9]*(?:-[a-z0-9]+)*"
    r"\.[a-z][a-z0-9]*(?:-[a-z0-9]+)*"
)
_ANY_ID = rf"(?:{_LEGACY_ID}|{_NAMESPACED_ID})"

_PATTERN_A = re.compile(rf'Violation\(\s*rule_id\s*=\s*"({_ANY_ID})"')
_PATTERN_B = re.compile(rf'\b([A-Z][A-Z0-9_]*)\s*=\s*"({_ANY_ID})"')
_PATTERN_C = re.compile(rf'\brule_id\s*=\s*"({_ANY_ID})"')

EMISSION_PATTERNS = (_PATTERN_A, _PATTERN_B, _PATTERN_C)


@dataclass(frozen=True)
class Emission:
    """One occurrence of a rule_id string literal in production source."""

    rule_id: str
    file_path: Path
    line: int


def extract_emissions(file_path: Path) -> Iterable[Emission]:
    """Yield every rule_id emission from *file_path*.

    Multiple patterns may match the same line; emissions are deduplicated by
    ``(file_path, line, rule_id)`` so a single ``RULE_ID = "<grammar>"``
    constant (matched by both pattern B and pattern C in slightly different
    scopes) only surfaces once.
    """
    try:
        text = file_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        _logger.debug(
            "rule_id_emission_extractor: skipping unreadable file %s: %s",
            file_path, exc,
            extra={"file": str(file_path), "error_type": type(exc).__name__},
        )
        return

    seen = set()
    for lineno, line in enumerate(text.splitlines(), start=1):
        for match in _PATTERN_A.finditer(line):
            rid = match.group(1)
            key = (str(file_path), lineno, rid)
            if key not in seen:
                seen.add(key)
                yield Emission(rule_id=rid, file_path=file_path, line=lineno)
        for match in _PATTERN_B.finditer(line):
            # group(1) = identifier, group(2) = rule_id grammar value
            rid = match.group(2)
            key = (str(file_path), lineno, rid)
            if key not in seen:
                seen.add(key)
                yield Emission(rule_id=rid, file_path=file_path, line=lineno)
        for match in _PATTERN_C.finditer(line):
            rid = match.group(1)
            key = (str(file_path), lineno, rid)
            if key not in seen:
                seen.add(key)
                yield Emission(rule_id=rid, file_path=file_path, line=lineno)


def iter_scan_files(roots: Sequence[Path]) -> Iterable[Path]:
    """Yield every production *.py file under *roots*.

    Excluded:
      - any file inside a ``tests/`` or ``fixtures/`` directory (anywhere)
      - ``__init__.py`` (no rule_id emissions are declared in package init)
      - ``__pycache__/`` artifacts

    Validator files named ``test_*.py`` directly under a scan root ARE
    included — those files are the production validators.
    """
    seen: set = set()
    for root in roots:
        if not Path(root).is_dir():
            continue
        for path in Path(root).rglob("*.py"):
            parts = set(path.parts)
            if "tests" in parts or "fixtures" in parts:
                continue
            if "__pycache__" in parts:
                continue
            if path.name == "__init__.py":
                continue
            key = str(path.resolve())
            if key in seen:
                continue
            seen.add(key)
            yield path


__all__ = [
    "EMISSION_PATTERNS",
    "Emission",
    "extract_emissions",
    "iter_scan_files",
]
