"""Runnable enforcement for tester.filename.urn (python-pytest).

Two layers, exactly as the no_collaborator_substitution re-proof:

  1. DETECTOR SELF-TESTS — pin the ported logic (URN-header recognition, top-level
     `def test_*` recognition, non-test files ignored, collectable names passed,
     mis-named intended tests flagged). Always green: they prove the detector is
     healthy.

  2. EMISSION (the v1.1 contract job, NOT a verdict) — scan `ATDD_SCAN_ROOTS`
     (with `ATDD_SCAN_EXCLUDES`) and write the RAW structured violations to
     `ATDD_VIOLATIONS_REPORT` for `run.py` to read back.

CRITICAL — this enforcement does NOT `assert violations == []`.
`tester.filename.urn` is `documentation-only` (advisory); whether the RAW
mis-named-test signal blocks is the DOWNSTREAM CONSUMER's disposition decision,
never the detector's. The detector emits the RAW list and the test passes once it
emits.

No core (`atdd.coach.*`) imports; the detector is imported by path.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest_test_filename as detector  # noqa: E402

_HERE = Path(__file__).resolve().parent

CONTRACT_VERSION = "1.1.0"
ENV_SCAN_ROOTS = "ATDD_SCAN_ROOTS"
ENV_SCAN_EXCLUDES = "ATDD_SCAN_EXCLUDES"
ENV_REPORT = "ATDD_VIOLATIONS_REPORT"


# ── 1. detector self-tests ────────────────────────────────────────────────────


def test_collectable_names() -> None:
    assert detector.is_pytest_collectable("test_login.py") is True
    assert detector.is_pytest_collectable("login_test.py") is True
    assert detector.is_pytest_collectable("login_checks.py") is False
    assert detector.is_pytest_collectable("verify_signup.py") is False


def test_urn_header_marks_a_test() -> None:
    src = "# URN: test:wagon:feat:C001-UNIT-001-x\n\ndef helper():\n    pass\n"
    is_test, lineno, line = detector.looks_like_test(src)
    assert is_test is True
    assert lineno == 1
    assert "URN: test:" in line


def test_top_level_test_def_marks_a_test() -> None:
    src = "def helper():\n    return 1\n\ndef test_thing():\n    assert helper()\n"
    is_test, lineno, line = detector.looks_like_test(src)
    assert is_test is True
    assert lineno == 4
    assert line.startswith("def test_thing")


def test_non_test_module_is_not_a_test() -> None:
    src = "def build_user(name):\n    return {'name': name}\n"
    assert detector.looks_like_test(src) == (False, 0, "")


def test_prose_mentioning_urn_marker_is_not_a_header() -> None:
    # A docstring/comment that merely MENTIONS "# URN: test:" mid-line is not a
    # real header; only a line-leading `# URN: test:` comment counts.
    src = '"""A helper. No `# URN: test:` header here."""\n\ndef build():\n    return 1\n'
    assert detector.looks_like_test(src) == (False, 0, "")


def test_indented_test_def_is_not_top_level() -> None:
    # A method named test_* inside a class body is not a module-level test fn.
    src = "class Thing:\n    def test_x(self):\n        return 1\n"
    assert detector.looks_like_test(src)[0] is False


def test_clean_fixture_has_no_violations() -> None:
    assert detector.scan_root(_HERE / "fixtures" / "clean") == []


def test_dirty_fixture_emits_two_raw_with_v11_shape() -> None:
    v = detector.scan_root(_HERE / "fixtures" / "dirty")
    assert len(v) == 2, f"expected 2 raw mis-named tests, got {len(v)}"
    files = sorted(item["file"] for item in v)
    assert files == ["login_checks.py", "verify_signup.py"]
    for item in v:
        assert item["rule_id"] == detector.RULE_FILENAME_URN
        assert set(item) >= {"rule_id", "file", "line", "col", "evidence", "source_line"}
        assert isinstance(item["source_line"], str)
    # The URN-headed file is reported at its header line; the def-only file at its def.
    by_file = {item["file"]: item for item in v}
    assert "URN: test:" in by_file["login_checks.py"]["source_line"]
    assert by_file["verify_signup.py"]["source_line"].startswith("def test_signup")


def test_collectable_test_file_is_not_flagged() -> None:
    # The clean fixture's correctly-named test_*.py is collectable -> ignored.
    v = detector.scan_root(_HERE / "fixtures" / "clean")
    assert all("user_connection" not in item["file"] for item in v)


# ── 2. emission (writes the RAW report; does NOT decide disposition) ───────────


def _scan_roots() -> list[Path]:
    raw = os.environ.get(ENV_SCAN_ROOTS)
    if raw:
        try:
            names = json.loads(raw)
        except json.JSONDecodeError:
            names = []
    else:
        single = os.environ.get("ATDD_SCAN_TARGET", "fixtures/clean")
        names = [single]
    roots: list[Path] = []
    for n in names:
        p = Path(n)
        roots.append(p if p.is_absolute() else (_HERE / p))
    return roots


def _exclude_globs() -> list[str]:
    raw = os.environ.get(ENV_SCAN_EXCLUDES)
    if not raw:
        return []
    try:
        globs = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return [str(g) for g in globs] if isinstance(globs, list) else []


def test_emit_raw_filename_report() -> None:
    """Scan the supplied roots and emit the RAW violation report (NOT a verdict)."""
    roots = _scan_roots()
    violations = detector.scan_roots(roots, _exclude_globs())

    report_path = os.environ.get(ENV_REPORT)
    if report_path:
        payload = {
            "contract_version": CONTRACT_VERSION,
            "scan_roots": [str(r) for r in roots],
            "violations": violations,
        }
        Path(report_path).write_text(json.dumps(payload, indent=2), encoding="utf-8")

    # Run-health only: deliberately NOT gated on emptiness.
    assert isinstance(violations, list)
