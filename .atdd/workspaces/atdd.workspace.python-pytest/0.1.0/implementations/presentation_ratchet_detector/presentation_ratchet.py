"""python-pytest detector for coder.refactor.coach-ratchet-pres.

Realizes the agnostic "presentation-layer reductions require smoke evidence"
obligation (disposition **advisory** + gate, severity 3). It flags any
presentation-layer file (`*/presentation/*.{tsx,ts,py}`) whose line count dropped
by MORE than 20% in a change set. The obligation exists because mechanical ratchet
trimming (line-count / duplication metrics) can silently gut user-visible features
— a past incident removed 8 match features during a trim while structural
validators stayed green (core issue #358, replacing #319).

THIS VALIDATOR DOES NOT CLEANLY FIT THE SCAN-MOUNT MODEL — and that is documented
honestly (see PHASE05-PROOF §6.5 long-tail note and this wave's final report). Its
input is NOT a directory snapshot but a GIT DIFF (base..head line-count deltas).
Following the v1.1 philosophy that scope is *supplied, not auto-discovered*
(CONTRACT §2), the diff facts the consumer/resolver would compute from git are
mounted into the scan root as a ``reductions.json`` manifest:

    { "reductions": [ { "path": "...", "before_lines": N, "after_lines": M,
                        "issue": K }, ... ] }

The detector reads that manifest, applies the SAME pure predicate as core
(`detect_presentation_reductions`), and emits one RAW violation per qualifying
reduction. It carries the originating ``issue`` number so the downstream consumer
can apply the smoke-evidence gate (which is disposition, not detection).

PROVENANCE — ported from core
    src/atdd/coder/validators/presentation_ratchet.py
        :: PRESENTATION_GLOBS / DEFAULT_THRESHOLD / PresentationReduction /
           _is_presentation_path / detect_presentation_reductions
    (origin/main @ 624d3afe, blob 5527bd51959f3ab5). The pure predicate is copied
    verbatim; the ``atdd.coach.*`` couplings were REMOVED.

DECOUPLED FROM CORE (every adaptation, per task §3):
  * ``bind_rule(...)``  -> module-level ``RULE_RATCHET_PRES`` constant. Severity 3
    / disposition advisory live in the convention node.
  * ``Violation``  -> plain dicts in the v1.1 shape
    ``{rule_id, file, line, col, evidence, source_line}`` plus an extra factual
    ``issue`` field (run.py preserves extra keys) so the consumer can locate the
    smoke evidence. The detail string is preserved verbatim from core
    ``PresentationRatchetRule.violations_for``.
  * ``collect_repo_reductions`` (git subprocess) -> REPLACED by a mounted
    ``reductions.json`` manifest (the resolver's git-diff facts), so the detector
    is hermetic and stdlib-only — no git, no `find_repo_root`.
  * ``PresentationRatchetRule.violations_for(reductions, has_evidence)`` /
    ``has_smoke_evidence``  -> the evidence GATE is NOT applied here. Core folds
    evidence into emission (returns [] when has_evidence). That conflates
    detection with disposition. This detector emits the RAW reduction REGARDLESS
    of evidence; the smoke-evidence gate is the downstream consumer's call (§1) —
    exactly the suppress-and-clean separation, with smoke evidence playing the
    role the inline marker plays for `coder.logging.structured`.

Pure stdlib (``json``, ``fnmatch``, ``pathlib``) — no third-party or core imports.
"""
from __future__ import annotations

import fnmatch
import json
from pathlib import Path

RULE_RATCHET_PRES = "coder.refactor.coach-ratchet-pres"  # disposition: advisory + gate

# Copied verbatim from core (issue #358 Phase 1 / Decision #1).
PRESENTATION_GLOBS = (
    "*/presentation/*.tsx",
    "*/presentation/*.ts",
    "*/presentation/*.py",
)
DEFAULT_THRESHOLD = 0.20

REDUCTIONS_MANIFEST = "reductions.json"


def is_presentation_path(path: str, globs=PRESENTATION_GLOBS) -> bool:
    return any(fnmatch.fnmatch(path, g) for g in globs)


def detect_presentation_reductions(diffs, threshold: float = DEFAULT_THRESHOLD,
                                   presentation_globs=PRESENTATION_GLOBS) -> list[dict]:
    """Filter ``(path, before, after, issue)`` facts to flagged reductions.

    Flagged when: path matches a presentation glob, ``before > 0`` (skip new
    files), ``after < before``, and ``(before - after) / before > threshold``
    (strict — exactly 20% is allowed). Mirrors core ``detect_presentation_reductions``.
    """
    out: list[dict] = []
    for path, before, after, issue in diffs:
        if before <= 0:
            continue
        if after >= before:
            continue
        if not is_presentation_path(path, presentation_globs):
            continue
        ratio = (before - after) / before
        if ratio > threshold:
            out.append({
                "path": path,
                "before_lines": before,
                "after_lines": after,
                "reduction_ratio": ratio,
                "issue": issue,
            })
    return out


def _load_manifest(root: Path) -> list[tuple]:
    """Read the mounted reductions.json -> list of (path, before, after, issue)."""
    manifest = root / REDUCTIONS_MANIFEST
    if not manifest.is_file():
        return []
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return []
    rows = data.get("reductions") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        return []
    diffs: list[tuple] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        diffs.append((
            str(row.get("path", "")),
            int(row.get("before_lines", 0)),
            int(row.get("after_lines", 0)),
            row.get("issue"),
        ))
    return diffs


def _violation_for(reduction: dict) -> dict:
    pct = round(reduction["reduction_ratio"] * 100)
    # Detail string preserved verbatim from core PresentationRatchetRule.violations_for.
    detail = (
        f"Presentation file shrank {reduction['before_lines']} -> "
        f"{reduction['after_lines']} lines ({pct}%); record smoke evidence before REFACTOR."
    )
    return {
        "rule_id": RULE_RATCHET_PRES,
        "file": reduction["path"],
        "line": 1,
        "col": 0,
        "evidence": detail,
        # No source file line is meaningful for a diff-derived fact; carry the
        # factual reduction summary as the RAW "source_line".
        "source_line": (
            f"{reduction['path']}: {reduction['before_lines']}->"
            f"{reduction['after_lines']} ({pct}%) issue={reduction['issue']}"
        ),
        # Extra factual field (run.py preserves it) so the consumer's smoke-evidence
        # gate can locate .atdd/smoke-evidence/<issue>.yaml.
        "issue": reduction["issue"],
    }


def scan_root(root: Path, exclude_globs: list[str] | None = None) -> list[dict]:
    """Read the mounted reductions manifest under ``root`` and return RAW v1.1
    violation dicts for each >20% presentation-layer reduction.

    The detector NEVER consults smoke evidence — emitting the RAW reduction even
    when evidence exists is the whole point of the separation (the gate is applied
    downstream by the consumer, like the all_suppressed crux for s&c rules)."""
    root = Path(root)
    reductions = detect_presentation_reductions(_load_manifest(root))
    return [_violation_for(r) for r in reductions]


def scan_roots(roots: list[Path], exclude_globs: list[str] | None = None) -> list[dict]:
    out: list[dict] = []
    for r in roots:
        out.extend(scan_root(Path(r), exclude_globs))
    return out
