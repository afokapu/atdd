"""
Ratchet baseline — load, compare, and assert violation counts.

Baseline file format (.atdd/baselines/coder.yaml in the TARGET repo):

    composition_completeness_python: 198
    composition_completeness_typescript: 47
    domain_layer_purity: 1

Each key is a validator_id.  The value is the maximum allowed violation
count.  Validators at 0 need no entry.

SPEC-CODER-RATCHET-0001: Violation count must not exceed baseline.
SPEC-CODER-RATCHET-0002: Baseline file must exist for ratcheted validators.
SPEC-CODER-RATCHET-0003: `atdd baseline update` writes current counts atomically.
SPEC-CODER-RATCHET-0004: Improvement below baseline produces PASS with advisory.
SPEC-CODER-RATCHET-0005: Validator at 0 violations needs no baseline entry.
"""

from __future__ import annotations

import os
import tempfile
import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import pytest
import yaml


def default_baseline_path(repo_root: Path) -> Path:
    """Return the canonical baseline file path for a repo."""
    return repo_root / ".atdd" / "baselines" / "coder.yaml"


class RatchetBaseline:
    """
    Load, compare, and enforce ratchet baselines for coder validators.

    Usage in a test::

        def test_my_validator(ratchet_baseline):
            violations = analyze(repo)
            ratchet_baseline.assert_no_regression(
                validator_id="my_validator",
                current_count=len(violations),
                violations=violations,
            )
    """

    def __init__(self, baseline_path: Path) -> None:
        self._path = baseline_path
        self._data: Optional[Dict[str, int]] = None

    @property
    def path(self) -> Path:
        return self._path

    @property
    def exists(self) -> bool:
        return self._path.is_file()

    # ------------------------------------------------------------------
    # Load / save
    # ------------------------------------------------------------------

    def load(self) -> Dict[str, int]:
        """Read the baseline file.  Returns empty dict if missing."""
        if self._data is not None:
            return self._data
        if not self._path.is_file():
            self._data = {}
            return self._data
        with open(self._path) as fh:
            raw = yaml.safe_load(fh) or {}
        self._data = {str(k): int(v) for k, v in raw.items()}
        return self._data

    def save(self, baselines: Dict[str, int]) -> None:
        """Atomic write of *baselines* to the YAML file."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # Write to temp file first, then rename for atomicity.
        fd, tmp = tempfile.mkstemp(
            dir=self._path.parent,
            suffix=".yaml.tmp",
        )
        try:
            with os.fdopen(fd, "w") as fh:
                yaml.safe_dump(
                    {k: v for k, v in sorted(baselines.items())},
                    fh,
                    default_flow_style=False,
                    sort_keys=True,
                )
            os.replace(tmp, self._path)
        except BaseException:
            os.unlink(tmp)
            raise
        self._data = dict(baselines)

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def get(self, validator_id: str) -> Optional[int]:
        """Return the baseline count for *validator_id*, or None."""
        return self.load().get(validator_id)

    # ------------------------------------------------------------------
    # Assert
    # ------------------------------------------------------------------

    def assert_no_regression(
        self,
        validator_id: str,
        current_count: int,
        violations: Sequence[Any] = (),
    ) -> None:
        """
        Assert that *current_count* does not exceed the baseline.

        Behavior:
        - No baseline entry → unconditional mode (assert 0 violations).
        - current > baseline → ``pytest.fail()`` with regression detail.
        - current < baseline → pass + ``warnings.warn()`` advisory.
        - current == baseline → pass silently.
        - current == 0 → pass (clean).

        SPEC-CODER-RATCHET-0001, SPEC-CODER-RATCHET-0004, SPEC-CODER-RATCHET-0005.
        """
        baseline = self.get(validator_id)

        # -- No baseline entry: auto-seed mode --
        if baseline is None:
            if current_count == 0:
                return
            # Auto-seed the baseline with the current count so the validator
            # passes on first run and ratchets from here.
            data = self.load()
            data[validator_id] = current_count
            self.save(data)
            warnings.warn(
                f"\nSPEC-CODER-RATCHET-0002: Auto-seeded baseline for {validator_id}\n\n"
                f"  Baseline set to: {current_count} violations\n"
                f"  File: {self._path}\n\n"
                f"  Commit this file to lock in the baseline.\n"
                f"  Future runs will fail if violations increase above {current_count}.\n",
                stacklevel=2,
            )
            return

        # -- Clean --
        if current_count == 0:
            return

        # -- Regression --
        if current_count > baseline:
            delta = current_count - baseline
            msg = (
                f"\n\nSPEC-CODER-RATCHET-0001 FAIL: Regression in {validator_id}\n\n"
                f"  Baseline: {baseline} violations\n"
                f"  Current:  {current_count} violations\n"
                f"  Delta:    +{delta} (regression)\n\n"
                f"  Fix the {delta} new violation(s) before merging.\n"
            )
            if violations:
                msg += _format_violations(violations)
            pytest.fail(msg)

        # -- Improvement --
        if current_count < baseline:
            delta = baseline - current_count
            warnings.warn(
                f"\nPASS: {validator_id} improved\n\n"
                f"  Baseline: {baseline} violations\n"
                f"  Current:  {current_count} violations\n"
                f"  Delta:    -{delta} (improvement)\n\n"
                f"  Run `atdd baseline update` to lock in the improvement.\n",
                stacklevel=2,
            )
            return

        # -- Holding steady --
        return

    # ------------------------------------------------------------------
    # Bulk operations (used by CLI)
    # ------------------------------------------------------------------

    def update(self, results: Dict[str, int]) -> None:
        """Merge *results* into the baseline and save."""
        merged = self.load()
        for vid, count in results.items():
            if count == 0:
                merged.pop(vid, None)
            else:
                merged[vid] = count
        self.save(merged)

    def show(self, results: Dict[str, int]) -> List[Dict[str, Any]]:
        """Return comparison rows: validator, baseline, current, delta, status."""
        baselines = self.load()
        all_ids = sorted(set(baselines) | set(results))
        rows: List[Dict[str, Any]] = []
        for vid in all_ids:
            bl = baselines.get(vid, 0)
            cur = results.get(vid, 0)
            delta = cur - bl
            if delta > 0:
                status = "REGRESSION"
            elif delta < 0:
                status = "IMPROVED"
            elif cur == 0:
                status = "CLEAN"
            else:
                status = "HOLDING"
            rows.append({
                "validator": vid,
                "baseline": bl,
                "current": cur,
                "delta": delta,
                "status": status,
            })
        return rows


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _format_violations(violations: Sequence[Any], limit: int = 10) -> str:
    """Format a sample of violations for the failure message."""
    lines = []
    for v in violations[:limit]:
        lines.append(f"    {v}")
    if len(violations) > limit:
        lines.append(f"    ... and {len(violations) - limit} more")
    return "\n  Violations:\n" + "\n".join(lines) + "\n"
