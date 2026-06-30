"""Runnable enforcement for coder.dead-code.reachability-typescript under python-pytest.

A PYTHON pytest module that inspects TypeScript source (regex over import
specifiers — no TS runtime needed), mirroring core test_dead_code_typescript.py.

Two layers: detector self-tests (root classification, import-edge resolution, an
orphan is flagged, index.ts is never flagged), then EMISSION of the RAW report to
``ATDD_VIOLATIONS_REPORT``. ``coder.dead-code.reachability-typescript`` is
``strict``; the strict verdict is the downstream consumer's job — the test
asserts run-health, not emptiness.

No core (``atdd.coach.*``) imports; the detector is imported by path.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

import dead_code_typescript as detector  # noqa: E402

_HERE = Path(__file__).resolve().parent

CONTRACT_VERSION = "1.1.0"
ENV_SCAN_ROOTS = "ATDD_SCAN_ROOTS"
ENV_SCAN_EXCLUDES = "ATDD_SCAN_EXCLUDES"
ENV_REPORT = "ATDD_VIOLATIONS_REPORT"


# ── 1. detector self-tests ────────────────────────────────────────────────────


def test_root_classification() -> None:
    assert detector.is_root_file(Path("web/index.ts")) is True
    assert detector.is_root_file(Path("web/main.tsx")) is True
    assert detector.is_root_file(Path("web/foo.test.ts")) is True
    assert detector.is_root_file(Path("web/__tests__/h.ts")) is True
    assert detector.is_root_file(Path("web/widget.ts")) is False


def test_import_specifiers_are_extracted() -> None:
    # extract_import_paths operates on files; assert the regexes match specifiers.
    src = "import { run } from './app';\nexport { x } from './x';\n"
    found: list[str] = []
    for pat in detector._ALL_PATTERNS:
        found.extend(pat.findall(src))
    assert "./app" in found and "./x" in found


def test_clean_fixture_has_no_unreachable() -> None:
    assert detector.scan_root(_HERE / "fixtures" / "clean") == []


def test_dirty_fixture_flags_the_orphan_only() -> None:
    v = detector.scan_root(_HERE / "fixtures" / "dirty")
    files = {item["file"] for item in v}
    assert files == {"orphan.ts"}
    for item in v:
        assert item["rule_id"] == detector.RULE_DEAD_CODE_TS
        assert item["line"] == 1 and item["col"] == 0
        assert set(item) >= {"rule_id", "file", "line", "col", "evidence", "source_line"}


def test_index_barrels_are_never_flagged() -> None:
    v = detector.scan_root(_HERE / "fixtures" / "dirty")
    assert all(not item["file"].endswith("index.ts") for item in v)


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


def test_emit_raw_dead_code_ts_report() -> None:
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
