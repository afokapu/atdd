# URN: component:govern-lifecycle:bulk-suppress-backfill:backend:application
# Runtime: python
# Purpose: Bulk-insert inline suppress markers on pre-existing violation sites (issue #482).

"""
``atdd suppress backfill`` — bulk suppress codemod (issue #482).

Walks the rule's registered scanner to enumerate current violation sites,
then inserts a language-appropriate inline suppress comment on each
offending line idempotently.  Already-marked lines are skipped.

Language comment leaders:
    ``.py``          →  ``# atdd:suppress(<rule_id>) UNTIL=<date>``
    ``.ts`` / ``.tsx`` →  ``// atdd:suppress(<rule_id>) UNTIL=<date>``

Usage (CLI surface registered in cli.py):
    atdd suppress backfill --rule coder.logging.coach-silent-swallow --until 2026-Q4

Usage (programmatic):
    from atdd.coach.commands.suppress import suppress_backfill, BackfillResult
    result = suppress_backfill(rule_id="...", until="...", scanner=..., repo_root=...)
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional, Sequence, Tuple

import yaml

from atdd.coach.validators._violation import Violation


# ---------------------------------------------------------------------------
# Scanner registry
# ---------------------------------------------------------------------------
# Maps rule_id → callable(repo_root: Path) → (count, violations).
# Add entries here as new suppress-and-clean rules are introduced.

def _build_scanner_registry() -> dict[str, Callable[[Path], Tuple[int, List[Violation]]]]:
    registry: dict[str, Callable[[Path], Tuple[int, List[Violation]]]] = {}
    try:
        from atdd.coder.validators.test_no_silent_exception_swallowing_python import (
            scan_silent_swallows_python,
        )
        registry["coder.logging.coach-silent-swallow"] = scan_silent_swallows_python
    except ImportError:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2027-01-01
        pass
    return registry


SCANNER_REGISTRY: dict[str, Callable[[Path], Tuple[int, List[Violation]]]] = (
    _build_scanner_registry()
)


# ---------------------------------------------------------------------------
# BackfillResult
# ---------------------------------------------------------------------------

@dataclass
class BackfillResult:
    """Summary of a suppress_backfill run."""

    rule_id: str
    until: str
    edited_count: int = 0
    skipped_count: int = 0
    files_touched: List[Path] = field(default_factory=list)

    def __str__(self) -> str:
        files_str = (
            "\n  " + "\n  ".join(str(p) for p in self.files_touched)
            if self.files_touched
            else " (none)"
        )
        return (
            f"suppress backfill — rule={self.rule_id} until={self.until}\n"
            f"  edited:  {self.edited_count}\n"
            f"  skipped: {self.skipped_count} (already marked)\n"
            f"  files:  {files_str}"
        )


# ---------------------------------------------------------------------------
# Comment-leader selection
# ---------------------------------------------------------------------------

def _comment_leader(path: Path) -> str:
    if path.suffix in (".ts", ".tsx"):
        return "//"
    return "#"


def _marker_text(rule_id: str, until: str, path: Path) -> str:
    leader = _comment_leader(path)
    return f"{leader} atdd:suppress({rule_id}) UNTIL={until}"


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def _marker_already_present(line: str, rule_id: str) -> bool:
    return f"atdd:suppress({rule_id})" in line


def _insert_marker(line: str, marker: str) -> str:
    """Append the marker to the line, preserving trailing newline."""
    stripped = line.rstrip("\n\r")
    eol = line[len(stripped):]
    return f"{stripped}  {marker}{eol}"


def suppress_backfill(
    rule_id: str,
    until: str,
    scanner: Callable[[Path], Tuple[int, List[Violation]]],
    repo_root: Path,
) -> BackfillResult:
    """Insert inline suppress markers on all violation sites returned by *scanner*.

    Args:
        rule_id: The rule identifier (e.g. ``"coder.logging.coach-silent-swallow"``).
        until: The UNTIL date string (e.g. ``"2026-Q4"`` or ``"2026-12-31"``).
        scanner: Callable ``(repo_root) → (count, violations)``.  The caller
            supplies this — either from SCANNER_REGISTRY or a test double.
        repo_root: Filesystem root passed to *scanner*.

    Returns:
        :class:`BackfillResult` with edited/skipped counts and files_touched.
    """
    _count, violations = scanner(repo_root)

    result = BackfillResult(rule_id=rule_id, until=until)

    # Group violations by file path
    by_file: dict[Path, List[int]] = {}
    for v in violations:
        # location is "path:line" or absolute "/abs/path:line"
        loc = v.location
        colon_idx = loc.rfind(":")
        if colon_idx == -1:
            continue
        path_str = loc[:colon_idx]
        try:
            lineno = int(loc[colon_idx + 1:])
        except ValueError:
            continue
        p = Path(path_str)
        by_file.setdefault(p, []).append(lineno)

    for file_path, line_numbers in by_file.items():
        try:
            original = file_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        lines = original.splitlines(keepends=True)
        file_edited = False

        for lineno in sorted(set(line_numbers)):
            idx = lineno - 1  # 0-based
            if idx < 0 or idx >= len(lines):
                continue
            if _marker_already_present(lines[idx], rule_id):
                result.skipped_count += 1
            else:
                marker = _marker_text(rule_id, until, file_path)
                lines[idx] = _insert_marker(lines[idx], marker)
                result.edited_count += 1
                file_edited = True

        if file_edited:
            file_path.write_text("".join(lines), encoding="utf-8")
            result.files_touched.append(file_path)

    # Count skipped from files that had no edits (marker already present)
    # already tracked in the loop above.

    return result


# ---------------------------------------------------------------------------
# Orphaned-baseline detection
# ---------------------------------------------------------------------------

_ORPHANED_KEY_PREFIXES = (
    "silent_exception_swallowing_",
    "ratchet_baseline_",
)


def check_orphaned_baseline_keys(repo_root: Path) -> List[str]:
    """Return WARN strings for orphaned integer-count keys in .atdd/baselines/coder.yaml.

    Detects keys left over from the old RatchetBaseline mechanism that the
    new disposition gate no longer reads.  Returns one warning string per
    orphaned key, or an empty list if the file is absent or contains no
    orphaned keys.
    """
    coder_yaml = repo_root / ".atdd" / "baselines" / "coder.yaml"
    if not coder_yaml.exists():
        return []

    try:
        data = yaml.safe_load(coder_yaml.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2027-01-01
        return []

    warnings: List[str] = []
    for key, value in data.items():
        if not isinstance(value, int):
            continue
        if any(key.startswith(prefix) for prefix in _ORPHANED_KEY_PREFIXES):
            warnings.append(
                f"WARN: orphaned-baseline-key {key!r} — safe to delete; "
                f"see substrate spec v12 §4.5 (issue #422). "
                f"This integer count is no longer read by the disposition gate."
            )
    return warnings


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def run_suppress_backfill(
    rule_id: str,
    until: str,
    repo_root: Optional[Path] = None,
    dry_run: bool = False,
    _scanner_override: Optional[Callable[[Path], Tuple[int, List[Violation]]]] = None,
) -> int:
    """Entry point called from ``cli.py`` for ``atdd suppress backfill``.

    Returns exit code (0 = success, 1 = error).
    """
    if repo_root is None:
        from atdd.coach.utils.repo import find_repo_root
        repo_root = find_repo_root()

    scanner: Optional[Callable[[Path], Tuple[int, List[Violation]]]] = _scanner_override
    if scanner is None:
        scanner = SCANNER_REGISTRY.get(rule_id)

    if scanner is None:
        msg = (
            f"Error: no scanner registered for rule_id={rule_id!r}.\n"
            f"Supported rules: {sorted(SCANNER_REGISTRY)}\n"
            f"To add support, register a scanner in "
            f"atdd.coach.commands.suppress.SCANNER_REGISTRY."
        )
        print(msg)
        return 1

    if dry_run:
        _count, violations = scanner(repo_root)
        print(f"[dry-run] suppress backfill — rule={rule_id} until={until}")
        print(f"  would mark {_count} violation(s)")
        for v in violations:
            print(f"  {v.location}: {v.detail}")
        return 0

    result = suppress_backfill(
        rule_id=rule_id,
        until=until,
        scanner=scanner,
        repo_root=repo_root,
    )

    print(result)
    return 0


__all__ = [
    "BackfillResult",
    "SCANNER_REGISTRY",
    "check_orphaned_baseline_keys",
    "run_suppress_backfill",
    "suppress_backfill",
]
