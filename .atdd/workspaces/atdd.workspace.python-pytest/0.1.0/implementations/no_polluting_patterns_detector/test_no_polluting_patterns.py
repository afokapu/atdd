"""Runnable enforcement for tester.test-isolation.no-polluting-patterns (python-pytest).

Two layers:

  1. DETECTOR SELF-TESTS — pin the ported AST logic (bare-init-bad-cwd flagged,
     core-bare-unscoped flagged, properly-scoped patterns clean, unparseable file
     yields []). Always green: they prove the detector is healthy.

  2. EMISSION (the v1.1 contract job, NOT a verdict) — scan ``ATDD_SCAN_ROOTS``
     (with ``ATDD_SCAN_EXCLUDES``) and write the RAW structured violations to
     ``ATDD_VIOLATIONS_REPORT`` for ``run.py`` to read back.

``tester.test-isolation.no-polluting-patterns`` is ``strict``; the detector still
only EMITS the RAW pollution-site list. The strict verdict (any site -> FAIL) is
the downstream consumer's disposition decision, never the detector's. The test
asserts run-health, not emptiness.

No core (``atdd.coach.*``) imports; the detector is imported by path.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

import no_polluting_patterns as detector  # noqa: E402

_HERE = Path(__file__).resolve().parent

CONTRACT_VERSION = "1.1.0"
ENV_SCAN_ROOTS = "ATDD_SCAN_ROOTS"
ENV_SCAN_EXCLUDES = "ATDD_SCAN_EXCLUDES"
ENV_REPORT = "ATDD_VIOLATIONS_REPORT"


# ── 1. detector self-tests ────────────────────────────────────────────────────


def test_bare_init_bad_cwd_is_flagged() -> None:
    src = (
        "import subprocess, os\n"
        "def test_x():\n"
        "    subprocess.run(['git','init','--bare','/tmp/r'], cwd=os.getcwd())\n"
    )
    hits = detector.detect_pollution(src)
    assert len(hits) == 1
    assert hits[0][2] == "bare-init-bad-cwd"


def test_core_bare_unscoped_is_flagged() -> None:
    src = (
        "import subprocess\n"
        "def test_x():\n"
        "    subprocess.run(['git','config','core.bare','true'])\n"
    )
    hits = detector.detect_pollution(src)
    assert len(hits) == 1
    assert hits[0][2] == "core-bare-unscoped"


def test_properly_scoped_patterns_are_clean() -> None:
    clean_snippets = [
        "import subprocess\ndef t(tmp_path):\n"
        "    subprocess.run(['git','init','--bare',str(tmp_path)], check=True)\n",
        "import subprocess\ndef t(tmp_path):\n"
        "    subprocess.run(['git','-C',str(tmp_path),'config','core.bare','true'])\n",
        "import subprocess\ndef t(tmp_path):\n"
        "    subprocess.run(['git','config','core.bare','true'], cwd=str(tmp_path))\n",
        "import subprocess\ndef t():\n"
        "    subprocess.run(['git','config','--worktree','core.bare','true'])\n",
    ]
    for src in clean_snippets:
        assert detector.detect_pollution(src) == [], src


def test_unparseable_file_yields_no_findings() -> None:
    assert detector.detect_pollution("def broken(\n") == []


def test_clean_fixture_has_no_pollution() -> None:
    assert detector.scan_root(_HERE / "fixtures" / "clean") == []


def test_dirty_fixture_emits_two_raw_with_v11_shape() -> None:
    v = detector.scan_root(_HERE / "fixtures" / "dirty")
    assert len(v) == 2, f"expected 2 raw pollution sites, got {len(v)}"
    patterns = {
        "bare-init-bad-cwd" if "bare-init-bad-cwd" in i["evidence"] else "core-bare-unscoped"
        for i in v
    }
    assert patterns == {"bare-init-bad-cwd", "core-bare-unscoped"}
    for item in v:
        assert item["rule_id"] == detector.RULE_NO_POLLUTING_PATTERNS
        assert item["line"] >= 1 and item["col"] >= 0
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


def test_emit_raw_pollution_report() -> None:
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

    assert isinstance(violations, list)
