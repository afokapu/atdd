"""Runnable enforcement for tester.acceptance-violation.metric-implementation-must-exist
(python-pytest).

Two layers, exactly as the no_collaborator_substitution re-proof:

  1. DETECTOR SELF-TESTS — pin the ported logic (block + inline signal.metric
     parsing, non-signal `metric:` keys ignored, two-root module lookup,
     compute()/passes() presence). Always green: they prove the detector is healthy.

  2. EMISSION (the v1.1 contract job, NOT a verdict) — scan `ATDD_SCAN_ROOTS`
     (with `ATDD_SCAN_EXCLUDES`) and write the RAW structured violations to
     `ATDD_VIOLATIONS_REPORT` for `run.py` to read back.

CRITICAL — this enforcement does NOT `assert violations == []`. The strict
disposition is the DOWNSTREAM CONSUMER's decision; the detector emits the RAW list
and the test passes once it emits.

No core (`atdd.coach.*`) imports; the detector is imported by path.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

import metric_implementation as detector  # noqa: E402

_HERE = Path(__file__).resolve().parent

CONTRACT_VERSION = "1.1.0"
ENV_SCAN_ROOTS = "ATDD_SCAN_ROOTS"
ENV_SCAN_EXCLUDES = "ATDD_SCAN_EXCLUDES"
ENV_REPORT = "ATDD_VIOLATIONS_REPORT"


# ── 1. detector self-tests ────────────────────────────────────────────────────


def test_block_form_metric_is_found() -> None:
    src = "signal:\n  metric: latency_p95\n  threshold: 200\n"
    decls = detector.find_metric_declarations(src)
    assert decls == [(2, "latency_p95", "  metric: latency_p95")]


def test_inline_form_metric_is_found() -> None:
    src = "acceptance:\n  signal: {metric: error_rate, threshold: 0.01}\n"
    decls = detector.find_metric_declarations(src)
    assert len(decls) == 1
    assert decls[0][1] == "error_rate"


def test_metric_key_not_under_signal_is_ignored() -> None:
    # A `metric:` that is not nested inside a `signal:` block is not a declaration.
    src = "metadata:\n  metric: vanity_number\n"
    assert detector.find_metric_declarations(src) == []


def test_signal_block_closes_on_dedent() -> None:
    # The `metric:` here belongs to a sibling mapping, not the closed signal block.
    src = "signal:\n  threshold: 1\nother:\n  metric: nope\n"
    assert detector.find_metric_declarations(src) == []


def test_module_ok_requires_compute_and_passes(tmp_path) -> None:
    mdir = tmp_path / ".atdd" / "metrics"
    mdir.mkdir(parents=True)
    (mdir / "good.py").write_text("def compute(r):\n    return 0\ndef passes(v,t):\n    return True\n")
    (mdir / "nocompute.py").write_text("def passes(v,t):\n    return True\n")
    assert detector.metric_module_ok(tmp_path, "good") is True
    assert detector.metric_module_ok(tmp_path, "nocompute") is False
    assert detector.metric_module_ok(tmp_path, "missing") is False


def test_toolkit_lookup_root_is_honored(tmp_path) -> None:
    mdir = tmp_path / "src" / "atdd" / "runners" / "metrics"
    mdir.mkdir(parents=True)
    (mdir / "shipped.py").write_text("def compute(r):\n    return 0\ndef passes(v,t):\n    return True\n")
    assert detector.metric_module_ok(tmp_path, "shipped") is True


def test_clean_fixture_has_no_violations() -> None:
    assert detector.scan_root(_HERE / "fixtures" / "clean") == []


def test_dirty_fixture_emits_two_raw_with_v11_shape() -> None:
    v = detector.scan_root(_HERE / "fixtures" / "dirty")
    assert len(v) == 2, f"expected 2 raw missing-metric impls, got {len(v)}"
    names = sorted(item["evidence"].split("'")[1] for item in v)
    assert names == ["error_rate", "timeout_rate"]
    for item in v:
        assert item["rule_id"] == detector.RULE_METRIC_IMPLEMENTATION_MUST_EXIST
        assert set(item) >= {"rule_id", "file", "line", "col", "evidence", "source_line"}
        assert isinstance(item["source_line"], str)


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


def test_emit_raw_metric_implementation_report() -> None:
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
