"""
Pure helper: resolve pyproject.toml version-bump conflicts produced by
`gh pr update-branch` during a merge cascade.

Issue #365 Phase 3 — Decision #4: auto-resolve pyproject.toml only; v1
covers the dominant conflict pattern (PATCH bumps), other shapes
fall through to manual resolution.

SPEC IDs: SPEC-COACH-ORCH-0010 (pyproject auto-resolve).
"""
from __future__ import annotations

import re

_CONFLICT_RE = re.compile(
    r"<<<<<<< [^\n]*\n(?P<a>.*?)\n=======\n(?P<b>.*?)\n    re.DOTALL,
)
_VERSION_LINE_RE = re.compile(r'^(\s*version\s*=\s*)"(\d+)\.(\d+)\.(\d+)"\s*$')


def _parse_version_only(block: str) -> tuple[int, int, int, str] | None:
    """If ``block`` is exactly one ``version = "x.y.z"`` line, return parts.

    Returns ``(major, minor, patch, full_line)`` or ``None`` otherwise.
    """
    lines = [line for line in block.splitlines() if line.strip()]
    if len(lines) != 1:
        return None
    m = _VERSION_LINE_RE.match(lines[0])
    if not m:
        return None
    return int(m.group(2)), int(m.group(3)), int(m.group(4)), lines[0]


def resolve_pyproject_version_conflict(text: str) -> str | None:
    """Resolve PATCH-only version conflicts. Return ``None`` if not auto-resolvable.

    Auto-resolves only when every conflict block in ``text`` is a single
    ``version = "x.y.z"`` line on each side AND the two sides agree on
    MAJOR and MINOR. The winner is the higher PATCH.
    """
    if "<<<<<<<" not in text:
        return None

    matches = list(_CONFLICT_RE.finditer(text))
    if not matches:
        return None

    replacements: list[tuple[int, int, str]] = []
    for m in matches:
        a = _parse_version_only(m.group("a"))
        b = _parse_version_only(m.group("b"))
        if a is None or b is None:
            return None
        if (a[0], a[1]) != (b[0], b[1]):
            return None
        winner_line = a[3] if a[2] >= b[2] else b[3]
        replacements.append((m.start(), m.end(), winner_line))

    out: list[str] = []
    cursor = 0
    for start, end, winner_line in replacements:
        out.append(text[cursor:start])
        out.append(winner_line)
        cursor = end
    out.append(text[cursor:])
    return "".join(out)
