"""Runnable enforcement for coder.dead-code.reachability under python-pytest.

Two layers:

  1. DETECTOR SELF-TESTS — pin the ported reachability logic (root classification,
     import-graph edge resolution, an orphan is flagged, __init__.py is never
     flagged). Always green: they prove the detector is healthy.

  2. EMISSION (the v1.1 contract job, NOT a verdict) — scan ``ATDD_SCAN_ROOTS``
     (with ``ATDD_SCAN_EXCLUDES``) and write the RAW structured violations to
     ``ATDD_VIOLATIONS_REPORT`` for ``run.py`` to read back.

``coder.dead-code.reachability`` is ``strict``; the detector still only EMITS the
RAW unreachable-file list. The strict verdict (any unreachable -> FAIL) is the
downstream consumer's disposition decision, never the detector's. The test
asserts run-health, not emptiness.

No core (``atdd.coach.*``) imports; the detector is imported by path.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

import dead_code_python as detector  # noqa: E402

_HERE = Path(__file__).resolve().parent

CONTRACT_VERSION = "1.1.0"
ENV_SCAN_ROOTS = "ATDD_SCAN_ROOTS"
ENV_SCAN_EXCLUDES = "ATDD_SCAN_EXCLUDES"
ENV_REPORT = "ATDD_VIOLATIONS_REPORT"


# ── 1. detector self-tests ────────────────────────────────────────────────────


def test_root_classification() -> None:
    assert detector.is_root_file(Path("pkg/composition.py")) is True
    assert detector.is_root_file(Path("pkg/conftest.py")) is True
    assert detector.is_root_file(Path("pkg/__init__.py")) is True
    assert detector.is_root_file(Path("pkg/test_x.py")) is True
    assert detector.is_root_file(Path("pkg/tests/helper.py")) is True
    assert detector.is_root_file(Path("pkg/service.py")) is False


def test_clean_fixture_has_no_unreachable() -> None:
    assert detector.scan_root(_HERE / "fixtures" / "clean") == []


def test_dirty_fixture_flags_the_orphan_only() -> None:
    v = detector.scan_root(_HERE / "fixtures" / "dirty")
    files = {item["file"] for item in v}
    assert files == {"orphan.py"}
    for item in v:
        assert item["rule_id"] == detector.RULE_DEAD_CODE_PY
        assert item["line"] == 1 and item["col"] == 0
        assert set(item) >= {"rule_id", "file", "line", "col", "evidence", "source_line"}


def test_init_files_are_never_flagged() -> None:
    # An unreferenced __init__.py is structural, not dead code.
    v = detector.scan_root(_HERE / "fixtures" / "dirty")
    assert all(not item["file"].endswith("__init__.py") for item in v)


# ── 1b. ATDD_GRAPH_ROOTS parity (PARITY-AUDIT-26 row 1) ───────────────────────
#
# The ``entrypoint`` fixture has one convention root (composition.py, reaches
# only itself), an entry-point module app.py, and lib.py imported ONLY by app.py.
# Legacy (test_dead_code_python.py::find_cli_entry_points, L296-331) adds the
# pyproject [project.scripts] module files as graph roots and does NOT flag them;
# the core enforce layer now forwards those resolved absolute paths to the
# detector via ATDD_GRAPH_ROOTS. These two tests are the load-bearing control:
# the SAME fixture flips verdict purely on the presence of the env var, proving
# the env contract — not anything else — gates entry-point reachability.

_ENTRYPOINT = _HERE / "fixtures" / "entrypoint"


def test_entrypoint_module_flagged_without_graph_roots(monkeypatch) -> None:
    # WITHOUT the env contract: app.py (entry point) and lib.py (reachable only
    # through it) are unreachable from convention roots -> falsely flagged dead.
    monkeypatch.delenv(detector.ENV_GRAPH_ROOTS, raising=False)
    files = {item["file"] for item in detector.scan_root(_ENTRYPOINT)}
    assert files == {"app.py", "lib.py"}


def test_entrypoint_module_not_flagged_with_graph_roots(monkeypatch) -> None:
    # WITH the entry-point module's absolute path in ATDD_GRAPH_ROOTS (exactly
    # what core's runner forwards): app.py becomes a graph root and lib.py is
    # reachable through it -> neither flagged. Matches legacy verdict.
    entry = _ENTRYPOINT / "app.py"
    monkeypatch.setenv(detector.ENV_GRAPH_ROOTS, json.dumps([str(entry)]))
    files = {item["file"] for item in detector.scan_root(_ENTRYPOINT)}
    assert files == set()


def test_graph_roots_from_env_tolerates_malformed(monkeypatch) -> None:
    # Unset / empty / non-JSON / non-list -> no extra roots (never raises).
    monkeypatch.delenv(detector.ENV_GRAPH_ROOTS, raising=False)
    assert detector.graph_roots_from_env() == set()
    for bad in ("", "   ", "{not json", '"a string"', "123"):
        monkeypatch.setenv(detector.ENV_GRAPH_ROOTS, bad)
        assert detector.graph_roots_from_env() == set()


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


def test_emit_raw_dead_code_report() -> None:
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
