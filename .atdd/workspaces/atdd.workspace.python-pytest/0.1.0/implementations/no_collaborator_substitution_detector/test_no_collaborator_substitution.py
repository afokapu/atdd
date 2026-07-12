"""Runnable enforcement for tester.smoke.no-collaborator-substitution (python-pytest).

Two layers, exactly as the silent-swallow re-proof:

  1. DETECTOR SELF-TESTS — pin the ported AST logic (setattr found, env methods
     exempt, local-fn-over-attr found, data assignment ignored, suppress-marked
     site STILL emitted, smoke-file gating). Always green: they prove the detector
     is healthy.

  2. EMISSION (the v1.1 contract job, NOT a verdict) — scan ``ATDD_SCAN_ROOTS``
     (with ``ATDD_SCAN_EXCLUDES``) and write the RAW structured violations to
     ``ATDD_VIOLATIONS_REPORT`` for ``run.py`` to read back.

CRITICAL — this enforcement does NOT ``assert violations == []``.
``tester.smoke.no-collaborator-substitution`` is ``suppress-and-clean``; whether a
``# atdd:suppress(...)`` marker absorbs a raw violation is the DOWNSTREAM
CONSUMER's disposition decision (§1), never the detector's. The detector emits the
RAW list — INCLUDING marked sites — and the test passes once it emits.

No core (``atdd.coach.*``) imports; the detector is imported by path.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

import no_collaborator_substitution as detector  # noqa: E402

_HERE = Path(__file__).resolve().parent

CONTRACT_VERSION = "1.1.0"
ENV_SCAN_ROOTS = "ATDD_SCAN_ROOTS"
ENV_SCAN_EXCLUDES = "ATDD_SCAN_EXCLUDES"
ENV_REPORT = "ATDD_VIOLATIONS_REPORT"


# ── 1. detector self-tests ────────────────────────────────────────────────────


def test_monkeypatch_setattr_is_detected() -> None:
    src = "def test_x(monkeypatch):\n    monkeypatch.setattr(obj, 'm', other)\n"
    hits = detector.detect_substitutions(src)
    assert len(hits) == 1
    assert "monkeypatch.setattr" in hits[0][2]


def test_monkeypatch_env_methods_are_exempt() -> None:
    # setenv / delenv / chdir / syspath_prepend are legitimate smoke setup.
    src = (
        "def test_x(monkeypatch, tmp_path):\n"
        "    monkeypatch.setenv('A', '1')\n"
        "    monkeypatch.delenv('B', raising=False)\n"
        "    monkeypatch.chdir(tmp_path)\n"
        "    monkeypatch.syspath_prepend('x')\n"
    )
    assert detector.detect_substitutions(src) == []


def test_local_function_over_attribute_is_detected() -> None:
    src = "def _fake(a):\n    return a\n\ndef test_x():\n    obj.method = _fake\n"
    hits = detector.detect_substitutions(src)
    assert len(hits) == 1
    assert "_fake" in hits[0][2]


def test_lambda_over_attribute_is_detected() -> None:
    src = "def test_x():\n    obj.method = lambda a: a\n"
    hits = detector.detect_substitutions(src)
    assert len(hits) == 1
    assert "<lambda>" in hits[0][2]


def test_data_assignment_over_attribute_is_ignored() -> None:
    # RHS is data (not a local def/lambda) — NOT a collaborator substitution.
    src = "def test_x(tmp_path):\n    self.path = tmp_path\n    obj.value = 7\n"
    assert detector.detect_substitutions(src) == []


def test_imported_function_over_attribute_is_ignored() -> None:
    # RHS resolves to an imported name, not a locally-defined callable (core parity).
    src = "from helpers import handler\n\ndef test_x():\n    obj.cb = handler\n"
    assert detector.detect_substitutions(src) == []


def test_marked_site_is_STILL_emitted_raw() -> None:
    # The detector emits even suppress-marked sites; absorbing is the consumer's job.
    src = (
        "def test_x(monkeypatch):\n"
        "    monkeypatch.setattr(obj, 'm', other)  "
        "# atdd:suppress(tester.smoke.no-collaborator-substitution)\n"
    )
    assert len(detector.detect_substitutions(src)) == 1


def test_smoke_file_gating() -> None:
    smoke = "# Phase: SMOKE\nx = 1\n"
    assert detector.is_smoke_test_file(Path("test_a.py"), smoke) is True
    assert detector.is_smoke_test_file(Path("a_test.py"), smoke) is True
    # A test file with no SMOKE marker is out of scope.
    assert detector.is_smoke_test_file(Path("test_a.py"), "x = 1\n") is False
    # A non-test file (even with the marker) is out of scope.
    assert detector.is_smoke_test_file(Path("service.py"), smoke) is False


def test_clean_fixture_has_no_substitutions() -> None:
    assert detector.scan_root(_HERE / "fixtures" / "clean") == []


def test_dirty_fixture_emits_three_raw_with_v11_shape() -> None:
    v = detector.scan_root(_HERE / "fixtures" / "dirty")
    assert len(v) == 3, f"expected 3 raw substitutions, got {len(v)}"
    for item in v:
        assert item["rule_id"] == detector.RULE_NO_COLLABORATOR_SUBSTITUTION
        assert set(item) >= {"rule_id", "file", "line", "col", "evidence", "source_line"}
        assert isinstance(item["source_line"], str)
    # Exactly one of the three carries an inline suppress marker (RAW still emits it).
    marked = [i for i in v if "atdd:suppress" in i["source_line"]]
    assert len(marked) == 1


def test_all_suppressed_fixture_still_emits_two_raw() -> None:
    v = detector.scan_root(_HERE / "fixtures" / "all_suppressed")
    assert len(v) == 2, f"expected 2 raw (both marked), got {len(v)}"
    assert all("atdd:suppress" in i["source_line"] for i in v)


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


def test_emit_raw_collaborator_substitution_report() -> None:
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
