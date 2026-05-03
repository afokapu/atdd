# URN: component:govern-lifecycle:enforcement-substrate:rule_id_registry_coherence:backend:domain
# Runtime: python
# Purpose: Surface emissions whose rule_id is not declared in any convention rules: block.

"""
Coach validator for rule-id registry coherence (issue #387).

Walks production validator + command source, extracts rule_id emissions via
three regex patterns (Decision #1), and cross-checks against the registry
built from every ``*.convention.yaml``. Drift surfaces as plain text:

  - permissive mode (default)     -> WARN, exit 0
  - ``ATDD_STRICT_COHERENCE=1``   -> ERROR, exit 1

The CLI flag ``--strict-coherence`` on ``atdd validate coach`` sets the
env var.

Decision #2: this validator does NOT emit ``Violation`` records for drift —
drift is a config issue, not a runtime violation. Plain text avoids
meta-recursion (a validator emitting violations about emissions).

Helper unit tests live under ``validators/tests/`` so their fixture string
literals are not picked up by this validator's own scan.
"""

from __future__ import annotations

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
        f"[WARN] rule_id_registry_coherence: "
        f"{len(drift)} emission(s) reference unregistered rule_id(s):"
    ]
    for fp, ln, rid in sorted(drift):
        try:
            rel = fp.resolve().relative_to(repo_root.resolve())
        except ValueError:
            rel = fp
        lines.append(f"  {rel}:{ln}   {rid}   not in any convention rules: block")
    lines.append("  Run with --strict-coherence to fail CI on this.")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tests / validator entry points
# ---------------------------------------------------------------------------
class TestCoherenceValidatorAgainstCurrentMain:
    """Smoke assertions against the live toolkit source."""

    def test_seeded_drift_id_surfaces(self):
        """The seeded drift example from #387: ``COACH-PRGATE-0003`` is
        declared in ``test_pr_phase_alignment.py`` but not in any convention
        rules: block.
        """
        roots = _scan_roots()
        assert roots, "no production scan roots resolved"

        registry = build_registry()
        unregistered = set()
        for f in iter_scan_files(roots):
            for e in extract_emissions(f):
                if e.rule_id not in registry:
                    unregistered.add(e.rule_id)

        seeded = "COACH-" + "PRGATE-0003"
        assert seeded in unregistered, (
            f"expected seed {seeded} in drift; got {sorted(unregistered)[:10]}..."
        )


@pytest.mark.coach
def test_rule_id_registry_coherence():
    """Permissive-mode coherence check.

    Default behavior: print a WARN block listing every emission whose
    rule_id is missing from the registry, then PASS (exit 0).

    Strict mode is opt-in via ``ATDD_STRICT_COHERENCE=1`` (the env var the
    CLI flag ``--strict-coherence`` sets) — when enabled, drift fails the
    test, which makes ``atdd validate coach`` exit 1.
    """
    drift = _collect_drift()
    if not drift:
        return  # registry is fully coherent; nothing to surface

    msg = _format_drift(drift)

    if os.environ.get("ATDD_STRICT_COHERENCE") == "1":
        pytest.fail(msg.replace("[WARN]", "[ERROR]"))
    else:
        # Plain-text WARN — visible in pytest -v output but does not fail.
        print("\n" + msg)
