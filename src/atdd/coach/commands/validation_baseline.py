"""
Validation Baseline
===================
Proof-of-execution baselines for ``atdd validate``.

After ``atdd validate <phase>`` passes locally, writes a baseline file to
``.atdd/baselines/validation/<phase>.yaml``.  CI can then verify the baseline
with ``atdd validate --verify-baseline`` in <10 s instead of re-running all
validators.

Baseline schema::

    phase: coach
    passed_at: "2026-04-08T14:30:00Z"
    source_hash: "abc123..."       # per-tree content hash of toolkit files
    atdd_version: "1.42.0"
    skipped_api: false

``source_hash`` is computed from the atdd **toolkit** files only (validators,
conventions, schemas for the phase) — NOT consumer repo code.  The ratchet
baseline handles consumer code violations separately.

SPEC-COACH-BASELINE-0001: atdd validate <phase> writes baseline on pass
SPEC-COACH-BASELINE-0002: atdd validate --verify-baseline completes in <10s
SPEC-COACH-BASELINE-0003: Stale baseline produces actionable error message
SPEC-COACH-BASELINE-0004: Validation baselines use separate namespace from ratchet
SPEC-COACH-BASELINE-0005: --skip-api recorded in baseline, accepted with warning
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml

import atdd
from atdd.coach.utils.repo import find_repo_root

# Phases whose toolkit files contribute to source_hash
PHASES = ("planner", "tester", "coder", "coach")

# Toolkit subdirectories hashed per phase
TOOLKIT_DIRS = ("validators", "conventions", "schemas")


# ---------------------------------------------------------------------------
# Content hashing (per-tree, NOT per-commit)
# ---------------------------------------------------------------------------

def _iter_toolkit_files(phase: str) -> list[Path]:
    """Return sorted list of toolkit files for *phase*.

    Toolkit files live inside the installed ``atdd`` package:
    ``src/atdd/<phase>/{validators,conventions,schemas}/**``
    """
    pkg_dir = Path(atdd.__file__).resolve().parent
    phase_dir = pkg_dir / phase
    files: list[Path] = []
    for subdir_name in TOOLKIT_DIRS:
        subdir = phase_dir / subdir_name
        if not subdir.is_dir():
            continue
        for f in subdir.rglob("*"):
            if f.is_file():
                files.append(f)
    files.sort()
    return files


def compute_source_hash(phase: str) -> str:
    """Compute a deterministic content hash over toolkit files for *phase*.

    If *phase* is ``"all"``, hashes all phases together.

    The hash is a SHA-256 of ``(relative_path + file_contents)`` for every
    toolkit file, sorted lexicographically by relative path.  This is a
    per-tree content hash — renaming a commit without touching files produces
    the same hash.
    """
    pkg_dir = Path(atdd.__file__).resolve().parent
    hasher = hashlib.sha256()

    phases = list(PHASES) if phase == "all" else [phase]
    for p in phases:
        for f in _iter_toolkit_files(p):
            rel = f.relative_to(pkg_dir)
            hasher.update(str(rel).encode())
            hasher.update(f.read_bytes())

    return hasher.hexdigest()


# ---------------------------------------------------------------------------
# Baseline paths
# ---------------------------------------------------------------------------

def validation_baseline_dir(repo_root: Path) -> Path:
    """Return ``.atdd/baselines/validation/`` for the target repo."""
    return repo_root / ".atdd" / "baselines" / "validation"


def validation_baseline_path(repo_root: Path, phase: str) -> Path:
    """Return the baseline file path for a given phase."""
    return validation_baseline_dir(repo_root) / f"{phase}.yaml"


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------

def write_validation_baseline(
    phase: str,
    skipped_api: bool = False,
    repo_root: Optional[Path] = None,
) -> Path:
    """Write a validation baseline after a successful ``atdd validate``.

    Returns the path of the written baseline file.
    """
    repo_root = repo_root or find_repo_root()
    source_hash = compute_source_hash(phase)

    data = {
        "phase": phase,
        "passed_at": datetime.now(timezone.utc).isoformat(),
        "source_hash": source_hash,
        "atdd_version": atdd.__version__,
        "skipped_api": skipped_api,
    }

    out = validation_baseline_path(repo_root, phase)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False))

    print(f"  Baseline written: {out.relative_to(repo_root)}")
    return out


# ---------------------------------------------------------------------------
# Verify
# ---------------------------------------------------------------------------

def verify_validation_baseline(
    phase: str = "all",
    repo_root: Optional[Path] = None,
) -> int:
    """Verify that the validation baseline is fresh.

    Recomputes the source hash and compares it to the stored baseline.
    Returns 0 on success, 1 on failure.
    """
    repo_root = repo_root or find_repo_root()

    phases = list(PHASES) if phase == "all" else [phase]
    failures: list[str] = []

    for p in phases:
        bl_path = validation_baseline_path(repo_root, p)

        if not bl_path.exists():
            failures.append(
                f"  {p}: MISSING — no baseline file.\n"
                f"         Run: atdd validate {p} --local"
            )
            continue

        stored = yaml.safe_load(bl_path.read_text())

        # Version check
        stored_version = stored.get("atdd_version", "unknown")
        if stored_version != atdd.__version__:
            failures.append(
                f"  {p}: STALE — atdd version changed "
                f"({stored_version} -> {atdd.__version__}).\n"
                f"         Run: atdd validate {p} --local"
            )
            continue

        # Source hash check
        current_hash = compute_source_hash(p)
        stored_hash = stored.get("source_hash", "")
        if current_hash != stored_hash:
            failures.append(
                f"  {p}: STALE — toolkit files changed.\n"
                f"         stored:  {stored_hash[:16]}...\n"
                f"         current: {current_hash[:16]}...\n"
                f"         Run: atdd validate {p} --local"
            )
            continue

        # Skip-api advisory
        if stored.get("skipped_api", False):
            print(f"  {p}: PASS (skipped_api=true — github_api tests were not run)")
        else:
            print(f"  {p}: PASS")

    if failures:
        print("\nBaseline verification FAILED:\n")
        for f in failures:
            print(f)
        print(
            "\nFix: re-run the failing phase(s) locally, then commit the "
            "updated baseline file(s)."
        )
        return 1

    print("\nAll baselines verified.")
    return 0
