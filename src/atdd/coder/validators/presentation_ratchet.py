# URN: component:govern-lifecycle:enforcement-substrate:PresentationRatchet:backend:application
# Runtime: python
# Purpose: Detect >20% line-count reductions in presentation-layer files and
#          require recorded smoke evidence before SMOKE→REFACTOR transition.

"""
COACH-RATCHET-PRES-001: Presentation ratchet smoke-gate detector.

Past incident (issue #319, replaced by #358): a worker trimming presentation
JSX to improve duplication / dead-code ratchets gutted real functionality.
Eight match features were removed during the trim; structural validators
reported success and the loss was discovered only via manual smoke testing
hours later.

This module:
  - Walks ``*/presentation/*.{tsx,ts,py}`` files in a PR diff.
  - Flags any file whose line count dropped by more than 20%.
  - Emits a structured ``Violation`` (rule_id ``COACH-RATCHET-PRES-001``,
    severity 3) when no smoke evidence exists for the issue.
  - Records / reads smoke evidence under ``.atdd/smoke-evidence/<N>.yaml``
    (gitignored — see Decision #3 in issue #358).

The detector is split into pure functions (used by unit tests) and a thin
git-driven entrypoint (``collect_repo_reductions``) so that the toolkit-self
pytest run on this branch exercises the same code path as a consumer repo.
"""

from __future__ import annotations

import datetime as _dt
import fnmatch
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple

import yaml

from atdd.coach.validators._violation import Violation


# Per issue body Phase 1: walk presentation files in three runtimes.
PRESENTATION_GLOBS: Tuple[str, ...] = (
    "*/presentation/*.tsx",
    "*/presentation/*.ts",
    "*/presentation/*.py",
)

# Decision #1 (issue body): 20% threshold (configurable via convention).
DEFAULT_THRESHOLD: float = 0.20


@dataclass(frozen=True)
class PresentationReduction:
    """One presentation-layer file whose line count dropped past threshold.

    ``reduction_ratio`` is ``(before - after) / before`` (0.0 - 1.0). A full
    deletion is represented as ``after_lines=0`` and ``reduction_ratio=1.0``
    (Decision #4: deletions are even more dangerous than trims).
    """

    path: str
    before_lines: int
    after_lines: int
    reduction_ratio: float


# ---------------------------------------------------------------------------
# Pure detector
# ---------------------------------------------------------------------------

def _is_presentation_path(path: str, globs: Sequence[str]) -> bool:
    return any(fnmatch.fnmatch(path, g) for g in globs)


def detect_presentation_reductions(
    diffs: Iterable[Tuple[str, int, int]],
    threshold: float = DEFAULT_THRESHOLD,
    presentation_globs: Sequence[str] = PRESENTATION_GLOBS,
) -> List[PresentationReduction]:
    """Filter ``(path, before_lines, after_lines)`` tuples to flagged reductions.

    A reduction is flagged when:
      - the path matches one of ``presentation_globs``, AND
      - ``before_lines > 0`` (skip new files), AND
      - ``(before - after) / before > threshold`` (strict — exactly 20% is OK).
    """
    out: List[PresentationReduction] = []
    for path, before, after in diffs:
        if before <= 0:
            continue
        if after >= before:
            continue
        if not _is_presentation_path(path, presentation_globs):
            continue
        ratio = (before - after) / before
        if ratio > threshold:
            out.append(PresentationReduction(
                path=path,
                before_lines=before,
                after_lines=after,
                reduction_ratio=ratio,
            ))
    return out


# ---------------------------------------------------------------------------
# Smoke evidence (.atdd/smoke-evidence/<issue>.yaml)
# ---------------------------------------------------------------------------

def smoke_evidence_dir(repo_root: Path) -> Path:
    return Path(repo_root) / ".atdd" / "smoke-evidence"


def smoke_evidence_path(repo_root: Path, issue_number: int) -> Path:
    return smoke_evidence_dir(repo_root) / f"{issue_number}.yaml"


def has_smoke_evidence(repo_root: Path, issue_number: int) -> bool:
    return smoke_evidence_path(repo_root, issue_number).is_file()


def record_smoke_evidence(
    repo_root: Path,
    issue_number: int,
    recorded_by: str,
    note: str = "",
) -> Path:
    """Write the evidence file. Gitignored, so cheap to overwrite."""
    target = smoke_evidence_path(repo_root, issue_number)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "issue": issue_number,
        "recorded_by": recorded_by,
        "recorded_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "note": note,
    }
    target.write_text(yaml.safe_dump(payload, sort_keys=True))
    return target


# ---------------------------------------------------------------------------
# Rule emission (Violation construction)
# ---------------------------------------------------------------------------

class PresentationRatchetRule:
    """Stable rule identity for COACH-RATCHET-PRES-001.

    Severity 3 per Decision #5 — advisory + gate, not stop-the-world.
    """

    RULE_ID = "COACH-RATCHET-PRES-001"
    SEVERITY = 3

    @classmethod
    def violations_for(
        cls,
        reductions: Iterable[PresentationReduction],
        has_evidence: bool,
    ) -> List[Violation]:
        if has_evidence:
            return []
        out: List[Violation] = []
        for r in reductions:
            pct = round(r.reduction_ratio * 100)
            detail = (
                f"Presentation file shrank {r.before_lines} → {r.after_lines} "
                f"lines ({pct}%); record smoke evidence before REFACTOR."
            )
            out.append(Violation(
                rule_id=cls.RULE_ID,
                severity=cls.SEVERITY,
                location=f"{r.path}:1",
                detail=detail,
            ))
        return out


# ---------------------------------------------------------------------------
# Git-driven collection
# ---------------------------------------------------------------------------

def _git(repo_root: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", *args],
        cwd=str(repo_root),
        text=True,
    )


def _file_line_count(repo_root: Path, ref: str, path: str) -> int:
    """Return the line count of ``path`` at ``ref``. 0 if absent."""
    try:
        content = subprocess.check_output(
            ["git", "show", f"{ref}:{path}"],
            cwd=str(repo_root),
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError:
        return 0
    if not content:
        return 0
    # Match `wc -l` semantics: trailing newline counts the final line.
    return content.count("\n") + (0 if content.endswith("\n") else 1)


def collect_repo_reductions(
    repo_root: Path,
    base_ref: str = "origin/main",
    head_ref: str = "HEAD",
    presentation_globs: Sequence[str] = PRESENTATION_GLOBS,
    threshold: float = DEFAULT_THRESHOLD,
) -> List[PresentationReduction]:
    """Diff ``base_ref..head_ref`` and return flagged presentation reductions.

    Walks only files whose path matches ``presentation_globs`` to avoid
    spending git-show calls on the rest of the tree.
    """
    out = _git(repo_root, "diff", "--name-only", f"{base_ref}..{head_ref}")
    candidates = [
        line.strip() for line in out.splitlines() if line.strip()
    ]
    diffs: List[Tuple[str, int, int]] = []
    for path in candidates:
        if not _is_presentation_path(path, presentation_globs):
            continue
        before = _file_line_count(repo_root, base_ref, path)
        after = _file_line_count(repo_root, head_ref, path)
        diffs.append((path, before, after))
    return detect_presentation_reductions(
        diffs,
        threshold=threshold,
        presentation_globs=presentation_globs,
    )


# ---------------------------------------------------------------------------
# Public re-exports
# ---------------------------------------------------------------------------

__all__ = [
    "PRESENTATION_GLOBS",
    "DEFAULT_THRESHOLD",
    "PresentationReduction",
    "PresentationRatchetRule",
    "collect_repo_reductions",
    "detect_presentation_reductions",
    "has_smoke_evidence",
    "record_smoke_evidence",
    "smoke_evidence_dir",
    "smoke_evidence_path",
]
