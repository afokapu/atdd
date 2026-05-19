# URN: test:observe-and-correct:observer-runtime-and-rules:C002-UNIT-001-flags-monkeypatch-setattr
# Acceptance: acc:observe-and-correct:C002-UNIT-001-flags-monkeypatch-setattr
# Acceptance: acc:observe-and-correct:C002-UNIT-002-flags-local-def-over-attribute
# Acceptance: acc:observe-and-correct:C002-UNIT-003-does-not-flag-env-setup
# Acceptance: acc:observe-and-correct:C002-UNIT-004-phase-scoped-scan
# WMBT: wmbt:observe-and-correct:C002
# Phase: GREEN
# Layer: domain
# Runtime: python
# Purpose: Unit tests for the #704 Tier 1 collaborator-substitution detector.

"""Tests for ``test_smoke_no_collaborator_substitution`` (#704 Tier 1).

The detector is a pure function over a Python source string. These tests
exercise it directly and exercise ``collect_violations`` against a synthetic
``tmp_path`` tree — never against the live repo, so the validator's own
fixtures cannot be self-flagged.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from atdd.tester.validators.test_smoke_no_collaborator_substitution import (
    collect_violations,
    detect_substitutions,
)

pytestmark = [pytest.mark.tester]


# ---------------------------------------------------------------------------
# detect_substitutions — positive cases (must flag)
# ---------------------------------------------------------------------------


def test_flags_monkeypatch_setattr():
    src = (
        "def test_x(monkeypatch):\n"
        "    monkeypatch.setattr(mod, 'fn', lambda: None)\n"
    )
    hits = detect_substitutions(src)
    assert len(hits) >= 1
    assert any("monkeypatch.setattr" in d for _, d in hits)


def test_flags_local_def_assigned_over_attribute():
    """The lived observer incident: obj.method = <local def>."""
    src = (
        "def _synthetic():\n"
        "    return 1\n"
        "def test_x():\n"
        "    obs.collect_input = _synthetic\n"
    )
    hits = detect_substitutions(src)
    assert len(hits) == 1
    lineno, detail = hits[0]
    assert lineno == 4
    assert "obs.collect_input = _synthetic" in detail


def test_flags_lambda_assigned_over_attribute():
    src = "def test_x():\n    server.handler = lambda r: None\n"
    hits = detect_substitutions(src)
    assert len(hits) == 1
    assert "<lambda>" in hits[0][1]


# ---------------------------------------------------------------------------
# detect_substitutions — negative cases (must NOT flag)
# ---------------------------------------------------------------------------


def test_does_not_flag_monkeypatch_env_methods():
    """Environment setup is legitimate in a smoke test."""
    src = (
        "def test_x(monkeypatch, tmp_path):\n"
        "    monkeypatch.setenv('K', 'v')\n"
        "    monkeypatch.chdir(tmp_path)\n"
        "    monkeypatch.delenv('Q', raising=False)\n"
        "    monkeypatch.syspath_prepend('/x')\n"
    )
    assert detect_substitutions(src) == []


def test_does_not_flag_data_attribute_assignment():
    """obj.attr = <data> is not collaborator substitution."""
    src = (
        "def test_x(tmp_path):\n"
        "    self.path = tmp_path\n"
        "    cfg.retries = 3\n"
        "    obj.name = 'hello'\n"
    )
    assert detect_substitutions(src) == []


def test_does_not_flag_attribute_assigned_an_imported_name():
    """Stated Tier 1 limitation: an imported helper as RHS is NOT caught
    (the RHS does not resolve to a locally-defined function)."""
    src = (
        "from helpers import real_handler\n"
        "def test_x():\n"
        "    server.handler = real_handler\n"
    )
    assert detect_substitutions(src) == []


def test_syntax_error_surfaces_as_a_finding():
    """An unparseable smoke test is surfaced, not silently skipped."""
    hits = detect_substitutions("def test_x(:\n    pass\n")
    assert len(hits) == 1
    assert "unparseable" in hits[0][1]


# ---------------------------------------------------------------------------
# collect_violations — repo-scan integration against a tmp_path tree
# ---------------------------------------------------------------------------


def _write(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def test_collect_violations_scans_only_phase_smoke_files(tmp_path: Path):
    # A SMOKE test that substitutes a collaborator -> flagged.
    _write(
        tmp_path / "src" / "x" / "tests" / "test_a_smoke.py",
        "# Phase: SMOKE\n"
        "def _fake():\n    return 0\n"
        "def test_a():\n    obj.boundary = _fake\n",
    )
    # A non-SMOKE test with the same substitution -> NOT flagged (not in scope).
    _write(
        tmp_path / "src" / "x" / "tests" / "test_b_unit.py",
        "# Phase: GREEN\n"
        "def _fake():\n    return 0\n"
        "def test_b():\n    obj.boundary = _fake\n",
    )
    # A SMOKE test that is clean -> NOT flagged.
    _write(
        tmp_path / "src" / "x" / "tests" / "test_c_smoke.py",
        "# Phase: SMOKE\n"
        "def test_c(monkeypatch, tmp_path):\n    monkeypatch.chdir(tmp_path)\n",
    )

    violations = collect_violations(repo_root=tmp_path)

    assert len(violations) == 1
    v = violations[0]
    assert v.rule_id == "tester.smoke.no-collaborator-substitution"
    assert v.severity == 4
    assert v.location.startswith("src/x/tests/test_a_smoke.py:")
    assert v.location.endswith(":5")


def test_collect_violations_skips_pycache_and_vcs(tmp_path: Path):
    _write(
        tmp_path / "__pycache__" / "test_z_smoke.py",
        "# Phase: SMOKE\ndef _f():\n    return 0\ndef test_z():\n    o.b = _f\n",
    )
    assert collect_violations(repo_root=tmp_path) == []
