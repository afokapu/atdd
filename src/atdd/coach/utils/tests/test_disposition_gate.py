# URN: component:govern-lifecycle:enforcement-substrate:disposition_gate:backend:tests
# Runtime: python
# Purpose: Cover the three disposition modes + suppression-marker matching for issue #395.

"""
Unit tests for ``atdd.coach.utils.disposition_gate.assert_disposition_satisfied``.

These tests build a minimal fake registry in-memory (no convention I/O) and
synthesize ``Violation`` records pointing into a ``tmp_path`` workspace —
the gate reads those files when matching ``# atdd:suppress(...)`` markers.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict

import pytest

from atdd.coach.utils.disposition_gate import assert_disposition_satisfied
from atdd.coach.utils.rule_id_registry import RuleMetadata
from atdd.coach.validators._violation import Violation


def _meta(rule_id: str, disposition: str) -> RuleMetadata:
    return RuleMetadata(
        rule_id=rule_id,
        convention_path=Path("/dev/null"),
        severity=3,
        description="fixture rule",
        disposition=disposition,
    )


def _registry(*pairs: tuple[str, str]) -> Dict[str, RuleMetadata]:
    return {rid: _meta(rid, disp) for rid, disp in pairs}


def _write(path: Path, contents: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(contents, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Empty list — pass silently
# ---------------------------------------------------------------------------

def test_empty_violations_passes():
    assert_disposition_satisfied(
        validator_id="vid",
        violations=[],
        registry={},
    )


# ---------------------------------------------------------------------------
# strict — any violation fails
# ---------------------------------------------------------------------------

def test_strict_fails_on_any_violation(tmp_path):
    target = _write(tmp_path / "code.py", "print('x')\n")
    v = Violation(
        rule_id="LOG-PRINT-001",
        severity=3,
        location=f"{target.name}:1",
        detail="print() in production code",
    )
    with pytest.raises(pytest.fail.Exception) as excinfo:
        assert_disposition_satisfied(
            validator_id="print_in_production",
            violations=[v],
            registry=_registry(("LOG-PRINT-001", "strict")),
            repo_root=tmp_path,
        )
    msg = str(excinfo.value)
    assert "LOG-PRINT-001" in msg
    assert "disposition=strict" in msg
    assert "code.py:1" in msg


def test_unknown_rule_id_defaults_to_strict(tmp_path):
    target = _write(tmp_path / "x.py", "noop\n")
    v = Violation(
        rule_id="UNREGISTERED-001",
        severity=2,
        location=f"{target.name}:1",
        detail="who knows",
    )
    with pytest.raises(pytest.fail.Exception):
        assert_disposition_satisfied(
            validator_id="vid",
            violations=[v],
            registry={},  # empty registry
            repo_root=tmp_path,
        )


# ---------------------------------------------------------------------------
# suppress-and-clean — markers absorb pre-existing violations
# ---------------------------------------------------------------------------

def test_suppress_and_clean_with_marker_passes(tmp_path):
    target = _write(
        tmp_path / "code.py",
        "print('x')  # atdd:suppress(LOG-PRINT-001)\n",
    )
    v = Violation(
        rule_id="LOG-PRINT-001",
        severity=3,
        location=f"{target.name}:1",
        detail="print() in production code",
    )
    # Should pass silently — marker absorbs the violation.
    assert_disposition_satisfied(
        validator_id="print_in_production",
        violations=[v],
        registry=_registry(("LOG-PRINT-001", "suppress-and-clean")),
        repo_root=tmp_path,
    )


def test_suppress_and_clean_without_marker_fails(tmp_path):
    target = _write(tmp_path / "code.py", "print('x')\n")
    v = Violation(
        rule_id="LOG-PRINT-001",
        severity=3,
        location=f"{target.name}:1",
        detail="print() in production code",
    )
    with pytest.raises(pytest.fail.Exception) as excinfo:
        assert_disposition_satisfied(
            validator_id="print_in_production",
            violations=[v],
            registry=_registry(("LOG-PRINT-001", "suppress-and-clean")),
            repo_root=tmp_path,
        )
    msg = str(excinfo.value)
    assert "LOG-PRINT-001" in msg
    assert "atdd:suppress(LOG-PRINT-001)" in msg
    assert "UNTIL=" in msg


def test_suppress_and_clean_marker_with_until_passes(tmp_path):
    target = _write(
        tmp_path / "code.py",
        "print('x')  # atdd:suppress(LOG-PRINT-001) UNTIL=2099-01-01\n",
    )
    v = Violation(
        rule_id="LOG-PRINT-001",
        severity=3,
        location=f"{target.name}:1",
        detail="print() in production code",
    )
    assert_disposition_satisfied(
        validator_id="print_in_production",
        violations=[v],
        registry=_registry(("LOG-PRINT-001", "suppress-and-clean")),
        repo_root=tmp_path,
    )


def test_suppress_and_clean_partial_suppression(tmp_path):
    target = _write(
        tmp_path / "code.py",
        "print('a')  # atdd:suppress(LOG-PRINT-001)\n"
        "print('b')\n",
    )
    suppressed = Violation(
        rule_id="LOG-PRINT-001",
        severity=3,
        location=f"{target.name}:1",
        detail="print() in production code",
    )
    fresh = Violation(
        rule_id="LOG-PRINT-001",
        severity=3,
        location=f"{target.name}:2",
        detail="print() in production code",
    )
    with pytest.raises(pytest.fail.Exception) as excinfo:
        assert_disposition_satisfied(
            validator_id="print_in_production",
            violations=[suppressed, fresh],
            registry=_registry(("LOG-PRINT-001", "suppress-and-clean")),
            repo_root=tmp_path,
        )
    msg = str(excinfo.value)
    assert "1 unsuppressed" in msg
    assert "1 suppressed" in msg
    # The suppressed line:1 should NOT be in the punch list; line:2 should.
    assert "code.py:2" in msg


# ---------------------------------------------------------------------------
# advisory — warns and passes
# ---------------------------------------------------------------------------

def test_advisory_warns_and_passes(tmp_path, recwarn):
    target = _write(tmp_path / "code.py", "x\n")
    v = Violation(
        rule_id="STYLE-NIT-001",
        severity=1,
        location=f"{target.name}:1",
        detail="trailing whitespace",
    )
    assert_disposition_satisfied(
        validator_id="style_nits",
        violations=[v],
        registry=_registry(("STYLE-NIT-001", "advisory")),
        repo_root=tmp_path,
    )
    assert any("STYLE-NIT-001" in str(w.message) for w in recwarn.list)


# ---------------------------------------------------------------------------
# Mixed dispositions in one call
# ---------------------------------------------------------------------------

def test_mixed_dispositions_routed_independently(tmp_path):
    target = _write(
        tmp_path / "code.py",
        "print('a')\n"  # strict bucket — line 1
        "print('b')  # atdd:suppress(LOG-CLEAN-001)\n"  # suppress-and-clean — line 2
        "print('c')\n",  # advisory bucket — line 3
    )
    strict_v = Violation(
        rule_id="LOG-STRICT-001",
        severity=3,
        location=f"{target.name}:1",
        detail="strict",
    )
    suppressed_v = Violation(
        rule_id="LOG-CLEAN-001",
        severity=3,
        location=f"{target.name}:2",
        detail="suppressed",
    )
    advisory_v = Violation(
        rule_id="LOG-ADVISE-001",
        severity=1,
        location=f"{target.name}:3",
        detail="advisory",
    )
    with pytest.raises(pytest.fail.Exception) as excinfo:
        assert_disposition_satisfied(
            validator_id="mixed",
            violations=[strict_v, suppressed_v, advisory_v],
            registry=_registry(
                ("LOG-STRICT-001", "strict"),
                ("LOG-CLEAN-001", "suppress-and-clean"),
                ("LOG-ADVISE-001", "advisory"),
            ),
            repo_root=tmp_path,
        )
    msg = str(excinfo.value)
    assert "LOG-STRICT-001" in msg
    # Suppressed and advisory entries must NOT show up in the failure body
    assert "LOG-CLEAN-001" not in msg
    assert "LOG-ADVISE-001" not in msg


# ---------------------------------------------------------------------------
# Opaque legacy callers
# ---------------------------------------------------------------------------

def test_opaque_violations_default_strict():
    with pytest.raises(pytest.fail.Exception) as excinfo:
        assert_disposition_satisfied(
            validator_id="legacy",
            violations=["bare string violation"],
            registry={},
        )
    assert "legacy" in str(excinfo.value)
    assert "bare string violation" in str(excinfo.value)
