# URN: test:judge-ambiguous-decisions:judge-and-issue-review:D006-SMOKE-001-review-returns-parseable-verdict
# Acceptance: acc:judge-ambiguous-decisions:D006-SMOKE-001-review-returns-parseable-verdict
# WMBT: wmbt:judge-ambiguous-decisions:D006
# Phase: SMOKE
# Layer: integration
"""D006-SMOKE-001 — `atdd issue review <N>` returns a parseable
multi-pass aggregate verdict end-to-end.

Issue #721: against the real CLI dispatcher, real coach config, real
frozen schemas, and real filesystem aggregate writer, `atdd issue
review` must exit 0 with a schema-valid `aggregate.json` — no "no JSON
found in response", no `'str' object has no attribute 'get'`
rule-binding crash.

The LLM is stubbed (as in every atdd test), but the stub models the
*sandboxed* review LLM the bug is about: it has no `gh`, so if the
prompt does not already carry the issue body it cannot review and
fails exactly the way the live `atdd issue review 720` repro failed.
The host-side body fetch (`issue_review._fetch_issue_body`) is the seam
that makes the stub succeed — it is overridden in the subprocess runner
so no real `gh` is shelled out.

RED expectations (fail until GREEN ships): on current code the prompt
carries no issue body, the sandboxed stub raises `LLMUnavailable`, and
the CLI exits non-zero with "no JSON found in response" on stderr.
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
    return json.loads((SCHEMAS_DIR / "issue-review-aggregate.schema.json").read_text())


def _write_workspace(workspace: Path) -> None:
    (workspace / ".atdd").mkdir()
    (workspace / ".atdd" / "config.yaml").write_text(yaml.safe_dump({"version": "1.0"}))


def _run_cli(workspace: Path, *args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    src = str(REPO_ROOT / "src")
    env["PYTHONPATH"] = f"{src}{os.pathsep}{env.get('PYTHONPATH', '')}"
    runner = textwrap.dedent("""
        import sys
        from atdd.coach.commands import judge as _j
        from atdd.coach.commands import issue_review as _ir
        from atdd.coach.commands.judge import LLMUnavailable

        _BODY = "SENTINEL-ISSUE-BODY :: real issue text for #721"

        # Host-side issue-body fetch seam (issue #721 / D006-UNIT-001).
        # On current code `run()` never calls this, so the body is absent
        # from the prompt and the sandboxed stub below fails the review.
        _ir._fetch_issue_body = lambda n: _BODY

        _CONFORMANT = {
            "dimensions": {
                "systemic":          {"verdict": "pass", "findings": []},
                "ambiguities":       {"verdict": "pass", "findings": []},
                "gap":               {"verdict": "pass", "findings": []},
                "regression":        {"verdict": "pass", "findings": []},
                "comprehensiveness": {"verdict": "pass", "findings": []},
            }
        }


        class _SandboxedStub:
            \"\"\"A review LLM with no `gh` — fails unless handed the body.\"\"\"

            def invoke(self, prompt):
                if _BODY not in prompt:
                    raise LLMUnavailable(
                        "no JSON found in response (first 200 chars): "
                        "'I need permission to fetch issue #721 from GitHub.'"
                    )
                return _CONFORMANT


        for _name in ("haiku", "mini", "flash"):
            _j.register_llm_client(_name, lambda: _SandboxedStub())

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


def test_cli_review_returns_parseable_aggregate(tmp_path: Path):
    _write_workspace(tmp_path)
    proc = _run_cli(
        tmp_path,
        "issue", "review", "721",
        "--passes", "3",
        "--llms", "haiku,mini,flash",
    )

    assert proc.returncode == 0, (
        "atdd issue review must return a parseable verdict — the host "
        f"must inject the issue body so the review LLM never needs `gh`.\n"
        f"stderr=\n{proc.stderr}\nstdout=\n{proc.stdout}"
    )

    agg_path = tmp_path / ".atdd" / "runtime" / "issue-reviews" / "721" / "aggregate.json"
    assert agg_path.exists(), "aggregate.json must be written"

    agg = json.loads(agg_path.read_text())
    jsonschema.Draft202012Validator(_aggregate_schema()).validate(agg)
    assert agg["issue"] == 721
    assert agg["verdict"], "aggregate must carry a top-level routing verdict"


def test_cli_review_emits_no_prose_or_typeerror_failure(tmp_path: Path):
    _write_workspace(tmp_path)
    proc = _run_cli(
        tmp_path,
        "issue", "review", "721",
        "--passes", "3",
        "--llms", "haiku,mini,flash",
    )

    combined = (proc.stderr + proc.stdout).lower()
    assert "no json found" not in combined, (
        "the review LLM must never be asked to fetch the issue itself — "
        "the host injects the body, so no pass should fail with a prose reply"
    )
    assert "has no attribute" not in combined, (
        "no pass should abort with a `'str' object has no attribute 'get'` "
        "rule-binding crash"
    )
