# URN: test:judge-ambiguous-decisions:judge-and-issue-review:D005-SMOKE-001-issue-review-real-infrastructure
# Acceptance: acc:judge-ambiguous-decisions:D005-UNIT-001-multi-pass-cross-llm-discipline
# WMBT: wmbt:judge-ambiguous-decisions:D005
# Phase: SMOKE
# Layer: integration
"""SMOKE — `atdd issue review` exercised against the real CLI dispatcher,
real coach config, real frozen schemas, and real filesystem aggregate
writer.

Unit tests stub `_resolve_repo_root` indirectly via tmp_path chdir and
call `run(...)` directly; this file launches `python -m atdd issue review
<N> ...` as a subprocess and asserts that:

  1. The CLI dispatcher routes `issue review` to
     ``atdd.coach.commands.issue_review``.
  2. Per-pass JSON files land at the spec §6.10 / #483 path
     (``.atdd/runtime/issue-reviews/<N>/pass-<i>-<llm>.json``).
  3. The aggregate JSON validates against the frozen
     ``issue-review-aggregate.schema.json`` shipped in this repo.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import jsonschema
import pytest
import yaml


pytestmark = [pytest.mark.platform]


REPO_ROOT = Path(__file__).resolve().parents[5]
SCHEMAS_DIR = REPO_ROOT / "src" / "atdd" / "coach" / "schemas"


def _aggregate_schema() -> dict:
    return json.loads(
        (SCHEMAS_DIR / "issue-review-aggregate.schema.json").read_text()
    )


def _pass_schema() -> dict:
    return json.loads(
        (SCHEMAS_DIR / "issue-review-pass.response.schema.json").read_text()
    )


def _write_workspace(workspace: Path) -> None:
    (workspace / ".atdd").mkdir()
    (workspace / ".atdd" / "config.yaml").write_text(
        yaml.safe_dump({"version": "1.0"})
    )


def _run_cli(workspace: Path, *args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    src = str(REPO_ROOT / "src")
    env["PYTHONPATH"] = f"{src}{os.pathsep}{env.get('PYTHONPATH', '')}"
    runner = textwrap.dedent("""
        import sys
        from atdd.coach.commands import judge as _j


        class _Stub:
            def invoke(self, prompt):
                return {
                    "dimensions": {
                        "systemic":          {"verdict": "pass", "findings": []},
                        "ambiguities":       {"verdict": "pass", "findings": []},
                        "gap":               {"verdict": "pass", "findings": []},
                        "regression":        {"verdict": "pass", "findings": []},
                        "comprehensiveness": {"verdict": "pass", "findings": []},
                    }
                }


        for _name in ("haiku", "mini", "flash"):
            _j.register_llm_client(_name, lambda: _Stub())

        from atdd.cli import main as _cli_main
        sys.argv = ["atdd"] + sys.argv[1:]
        sys.exit(_cli_main() or 0)
    """).lstrip()
    return subprocess.run(
        [sys.executable, "-c", runner, *args],
        cwd=str(workspace),
        capture_output=True,
        text=True,
        env=env,
    )


def test_cli_dispatcher_routes_issue_review_and_writes_aggregate(tmp_path: Path):
    _write_workspace(tmp_path)
    proc = _run_cli(
        tmp_path,
        "issue", "review", "777",
        "--passes", "3",
        "--llms", "haiku,mini,flash",
    )
    assert proc.returncode == 0, (
        f"stderr=\n{proc.stderr}\nstdout=\n{proc.stdout}"
    )

    review_dir = tmp_path / ".atdd" / "runtime" / "issue-reviews" / "777"
    assert (review_dir / "pass-1-haiku.json").exists()
    assert (review_dir / "pass-2-mini.json").exists()
    assert (review_dir / "pass-3-flash.json").exists()
    agg_path = review_dir / "aggregate.json"
    assert agg_path.exists()

    pass_schema = _pass_schema()
    for path in sorted(review_dir.glob("pass-*.json")):
        record = json.loads(path.read_text())
        jsonschema.Draft202012Validator(pass_schema).validate(record)

    agg = json.loads(agg_path.read_text())
    jsonschema.Draft202012Validator(_aggregate_schema()).validate(agg)
    assert agg["verdict"] == "unanimous-pass"
    assert agg["issue"] == 777


def test_cli_passes_below_minimum_exits_nonzero(tmp_path: Path):
    _write_workspace(tmp_path)
    proc = _run_cli(
        tmp_path,
        "issue", "review", "778",
        "--passes", "1",
        "--llms", "haiku",
    )
    assert proc.returncode != 0
    assert "passes" in (proc.stderr + proc.stdout).lower()


def test_cli_idempotent_without_force(tmp_path: Path):
    _write_workspace(tmp_path)
    args = (
        "issue", "review", "779",
        "--passes", "2",
        "--llms", "haiku,mini",
    )
    proc1 = _run_cli(tmp_path, *args)
    assert proc1.returncode == 0

    review_dir = tmp_path / ".atdd" / "runtime" / "issue-reviews" / "779"
    pass_files = sorted(review_dir.glob("pass-*.json"))
    mtimes_before = {p.name: p.stat().st_mtime_ns for p in pass_files}

    proc2 = _run_cli(tmp_path, *args)
    assert proc2.returncode == 0
    mtimes_after = {p.name: p.stat().st_mtime_ns for p in sorted(review_dir.glob("pass-*.json"))}
    # Without --force, per-pass files were reused (mtime unchanged).
    assert mtimes_before == mtimes_after
