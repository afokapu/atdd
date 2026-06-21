# Acceptance: acc:define-plans:D001-SMOKE-001-help-lists-flags
# Acceptance: acc:define-plans:E001-SMOKE-001-text-flag-live
# Acceptance: acc:define-plans:E002-SMOKE-001-md-file-live
# Acceptance: acc:define-plans:E003-SMOKE-001-pdf-richdoc-live
# Acceptance: acc:define-plans:E004-SMOKE-001-dir-codebase-live
# Acceptance: acc:define-plans:E005-SMOKE-001-no-args-exit2-live
# Acceptance: acc:define-plans:C001-SMOKE-001-json-keys-live
# Acceptance: acc:define-plans:C002-SMOKE-001-clean-import-live
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""#760 task 7 — live-CLI SMOKE acceptances for the 8 define-plans WMBTs.

Each exercises the real `atdd plan` CLI shell (#758) via subprocess and
runs-or-fails — never self-skips (so it can satisfy the SMOKE phase honestly,
replacing the lifted `planner.wmbt.must-have-smoke-acceptance` suppression).
These cover the shell behaviour; the full decomposition session is #1139.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[4]


def _plan(args, cwd):
    env = {"PYTHONPATH": str(_SRC), "PATH": os.environ.get("PATH", ""), "HOME": str(cwd)}
    return subprocess.run([sys.executable, "-m", "atdd", "plan", *args],
                          cwd=str(cwd), env=env, capture_output=True, text=True, timeout=60)


def _json(r):
    # the brief JSON line may land on stdout or stderr (upgrade notices interleave)
    blob = (r.stdout or "") + "\n" + (r.stderr or "")
    lines = [ln for ln in blob.splitlines() if ln.strip().startswith("{")]
    assert lines, f"no JSON found: stdout={r.stdout!r} stderr={r.stderr!r}"
    return json.loads(lines[-1])


def test_d001_help_lists_flags(tmp_path):
    r = _plan(["--help"], tmp_path)
    assert r.returncode == 0, r.stderr
    for flag in ("--text", "--brief-out", "--json", "--quiet"):
        assert flag in r.stdout, f"{flag} missing from help"


def test_e001_text_flag_yields_text_source(tmp_path):
    r = _plan(["--text", "hello world", "--json"], tmp_path)
    assert r.returncode == 0, r.stderr
    src = _json(r)["sources"][0]
    assert src["type"] == "text" and src["value"] == "hello world"


def test_e002_md_classifies_as_file(tmp_path):
    (tmp_path / "spec.md").write_text("# spec\n", encoding="utf-8")
    r = _plan(["spec.md", "--json"], tmp_path)
    assert r.returncode == 0, r.stderr
    assert _json(r)["sources"][0]["type"] == "file"


def test_e003_pdf_classifies_as_rich_doc(tmp_path):
    (tmp_path / "doc.pdf").write_text("x", encoding="utf-8")
    r = _plan(["doc.pdf", "--json"], tmp_path)
    assert r.returncode == 0, r.stderr
    assert _json(r)["sources"][0]["type"] == "rich_doc"


def test_e004_dir_classifies_as_codebase(tmp_path):
    (tmp_path / "repo").mkdir()
    r = _plan(["repo", "--json"], tmp_path)
    assert r.returncode == 0, r.stderr
    assert _json(r)["sources"][0]["type"] == "codebase"


def test_e005_no_args_exits_2(tmp_path):
    r = _plan([], tmp_path)
    assert r.returncode == 2, f"expected exit 2, got {r.returncode}"


def test_c001_json_has_expected_keys(tmp_path):
    r = _plan(["--text", "x", "--json"], tmp_path)
    assert r.returncode == 0, r.stderr
    doc = _json(r)
    assert "sources" in doc and "brief_out" in doc


def test_c002_runs_end_to_end_clean_import(tmp_path):
    # the CLI executing proves the plan module imports with no git/coach runtime dep
    r = _plan(["--text", "x"], tmp_path)
    assert r.returncode == 0, r.stderr
