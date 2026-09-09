# URN: test:govern-lifecycle:govern-lifecycle:M003-SMOKE-001
# Acceptance: acc:govern-lifecycle:M003-SMOKE-001-the-live-tree-is-quiet-and-the-scan-still-bites
# WMBT: wmbt:govern-lifecycle:M003
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
# Smoke: true
# # Phase: SMOKE
# # Smoke: true

"""M003-SMOKE-001 — the advisory starts quiet on the real tree, and still bites.

Both halves are the acceptance, and neither is sufficient alone.

QUIET, because a report that is noisy on the day it ships is ignored by the time
it matters. Every finding on this tree has been triaged by a human and carries an
inline suppression with a reason — today that is two string constants in
`test_c014_unit_001_classifier_sees_this_repos_code.py`, both fed to a pure string
classifier that opens nothing, verified by running that file from a real
non-toolkit repo (11 passed).

STILL BITES, because "reports nothing" is also what a broken scan looks like, and
a scan that silently matched nothing would satisfy the first half forever. So a
file carrying the R005 shape is planted and must be reported.

Runs against the shipped validator corpus itself — no fixture tree — because the
thing under test is whether THIS repo is quiet, which a fixture cannot answer.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

pytestmark = [pytest.mark.coach, pytest.mark.platform]


def test_m003_smoke_001_the_live_tree_is_quiet_and_the_scan_still_bites():
    from atdd.coach.validators.test_platform_marker_on_toolkit_selftests import (
        _iter_validator_test_files,
        scan_toolkit_path_strings,
    )

    findings = scan_toolkit_path_strings(_iter_validator_test_files())

    assert findings == [], (
        "the advisory reports findings nobody has triaged. Each one is either a "
        "toolkit path something opens — which needs pytest.mark.platform — or a "
        "path used as data, which needs an inline suppression carrying the "
        "reason:\n  "
        + "\n  ".join(f"{f.location}: {f.detail}" for f in findings)
    )


def test_m003_smoke_001_the_scan_still_reports_a_planted_case():
    """Silence must mean 'nothing to say', not 'nothing works'."""
    from atdd.coach.validators.test_platform_marker_on_toolkit_selftests import (
        scan_toolkit_path_strings,
    )

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        planted = root / "test_planted.py"
        # The R005 shape verbatim: a toolkit path held as a string constant.
        planted.write_text(
            'VALIDATOR = "src/atdd/coach/validators/test_phase_label_projection_only.py"\n'
            "def test_x():\n"
            "    assert VALIDATOR\n",
            encoding="utf-8",
        )

        findings = scan_toolkit_path_strings([planted], repo_root=root)

    assert len(findings) == 1, (
        "the scan did not report a planted toolkit-path string, so the clean "
        "result above proves nothing — this is the failure mode where a guard "
        "passes forever because it matches nothing"
    )
