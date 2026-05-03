# URN: component:govern-lifecycle:enforcement-substrate:rule_id_registry_coherence:backend:domain
# Runtime: python
# Purpose: Surface emissions whose rule_id is not declared in any convention rules: block.

"""
Coach validator for rule-id registry coherence (issue #387, strict-flip #394).

Walks production validator + command source, extracts rule_id emissions via
three regex patterns (Decision #1), and cross-checks against the registry
built from every ``*.convention.yaml``. Drift surfaces as plain text:

  - strict mode (default)         -> ERROR, exit 1
  - ``ATDD_PERMISSIVE_COHERENCE=1`` -> WARN, exit 0 (opt-out)

The CLI flag ``--permissive-coherence`` on ``atdd validate coach`` sets the
opt-out env var. Issue #394 flipped the default: drift fails CI unless the
caller explicitly opts back into permissive mode.

Decision #2: this validator does NOT emit ``Violation`` records for drift —
drift is a config issue, not a runtime violation. Plain text avoids
meta-recursion (a validator emitting violations about emissions).

Helper unit tests live under ``validators/tests/`` so their fixture string
literals are not picked up by this validator's own scan.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import List, Tuple

import pytest

import atdd
from atdd.coach.utils.repo import find_repo_root
from atdd.coach.utils.rule_id_registry import build_registry
from atdd.coach.validators.rule_id_emission_extractor import (
    extract_emissions,
    iter_scan_files,
)


_logger = logging.getLogger(__name__)


pytestmark = [pytest.mark.coach, pytest.mark.platform]


# ---------------------------------------------------------------------------
# Path constants
# ---------------------------------------------------------------------------
ATDD_PKG_DIR = Path(atdd.__file__).resolve().parent

# Production scan surface:
#   validators/**/*.py + coach/commands/**/*.py
#   exclude:  **/tests/**, **/fixtures/**
_SCAN_ROOTS_REL = (
    ("coach", "validators"),
    ("coder", "validators"),
    ("tester", "validators"),
    ("planner", "validators"),
    ("coach", "commands"),
)


def _scan_roots() -> List[Path]:
    """Return absolute paths to every production scan root (toolkit + repo checkout)."""
    repo_src = find_repo_root() / "src" / "atdd"
    out: List[Path] = []
    seen = set()
    for parts in _SCAN_ROOTS_REL:
        for base in (ATDD_PKG_DIR, repo_src):
            cand = base.joinpath(*parts)
            key = str(cand.resolve())
            if cand.is_dir() and key not in seen:
                seen.add(key)
                out.append(cand)
    return out


def _collect_drift() -> List[Tuple[Path, int, str]]:
    """Return ``[(file_path, line, rule_id), ...]`` for unregistered emissions."""
    registry = build_registry()
    roots = _scan_roots()
    drift: List[Tuple[Path, int, str]] = []
    for f in iter_scan_files(roots):
        for e in extract_emissions(f):
            if e.rule_id not in registry:
                drift.append((e.file_path, e.line, e.rule_id))
    return drift


def _format_drift(drift: List[Tuple[Path, int, str]]) -> str:
    repo_root = find_repo_root()
    lines = [
        f"[ERROR] rule_id_registry_coherence: "
        f"{len(drift)} emission(s) reference unregistered rule_id(s):"
    ]
    for fp, ln, rid in sorted(drift):
        try:
            rel = fp.resolve().relative_to(repo_root.resolve())
        except ValueError:
            rel = fp
        lines.append(f"  {rel}:{ln}   {rid}   not in any convention rules: block")
    lines.append("  Run with --permissive-coherence to demote to WARN (opt-out).")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Validator entry point
# ---------------------------------------------------------------------------
@pytest.mark.coach
def test_rule_id_registry_coherence():
    """Strict-by-default coherence check (issue #394).

    Default behavior: any emission whose rule_id is missing from the
    convention registry fails the test, which makes ``atdd validate coach``
    exit 1.

    Permissive-mode opt-out: set ``ATDD_PERMISSIVE_COHERENCE=1`` (the env
    var the CLI flag ``--permissive-coherence`` sets) — drift logs as WARN
    and the gate passes. Use sparingly while migrating new rule_ids into
    convention files.
    """
    drift = _collect_drift()
    if not drift:
        return  # registry is fully coherent; nothing to surface

    msg = _format_drift(drift)

    if os.environ.get("ATDD_PERMISSIVE_COHERENCE") == "1":
        # Permissive-mode WARN — surfaces drift without failing the gate.
        _logger.warning(
            "rule_id_registry_coherence drift: %d unregistered emission(s)",
            len(drift),
            extra={"drift_count": len(drift), "validator": "rule_id_registry_coherence"},
        )
        for fp, ln, rid in sorted(drift):
            _logger.warning(
                "rule_id_registry_coherence: %s:%d %s not in any convention rules: block",
                fp, ln, rid,
                extra={"file": str(fp), "line": ln, "rule_id": rid},
            )
        return

    pytest.fail(msg)
