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
        "coach", "issue-review", "721",
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
        "coach", "issue-review", "721",
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


# ---------------------------------------------------------------------------
# Real-infrastructure smoke (issue #721 SMOKE phase)
#
# The tests above stub the LLM but exercise the real CLI dispatcher,
# schemas and filesystem. The tests below additionally exercise the real
# host-side seams the bug is about — `gh issue view` and the `atdd repo`
# graph walk — against a real ATDD issue. They `pytest.skip` (never fail)
# when that infrastructure is unavailable, so CI stays deterministic
# offline; a maintainer with `gh` auth gets the full real verification.
#
# Issue 508 is the permanent (closed) `atdd issue review` feature issue;
# it is mapped to the `judge-ambiguous-decisions` wagon in the manifest,
# so the graph walk resolves a real `## Architecture context` section.
# ---------------------------------------------------------------------------

_REAL_ISSUE = 508


def test_real_gh_fetch_returns_issue_body():
    """`_fetch_issue_body` resolves a real GitHub issue body host-side."""
    from atdd.coach.commands import issue_review

    body = issue_review._fetch_issue_body(_REAL_ISSUE)
    if body.startswith("(issue #"):
        pytest.skip("`gh issue view` unavailable/unauthenticated in this environment")

    assert len(body) > 200, "a real issue body should be substantial"
    assert "(issue #" not in body[:40], "must be the real body, not the placeholder"


def test_real_repo_graph_summary_resolves_for_wagon_mapped_issue():
    """`build_issue_architecture_context` returns the real graph neighborhood."""
    from atdd.coach.commands.issue_graph import build_issue_architecture_context

    graph = build_issue_architecture_context(_REAL_ISSUE, repo_root=REPO_ROOT)
    if graph is None:
        pytest.skip("issue not mapped to a wagon in this checkout's manifest")

    assert graph.startswith("## Architecture context")
    assert "wagon:judge-ambiguous-decisions" in graph
    assert "wmbt:judge-ambiguous-decisions:D006" in graph, (
        "the graph summary must reflect the live plan/ neighborhood"
    )


def test_real_render_prompt_carries_body_and_graph_inline():
    """The assembled review prompt carries the real body AND graph summary."""
    from atdd.coach.commands import issue_review
    from atdd.coach.commands.issue_graph import build_issue_architecture_context

    body = issue_review._fetch_issue_body(_REAL_ISSUE)
    if body.startswith("(issue #"):
        pytest.skip("`gh issue view` unavailable/unauthenticated in this environment")
    graph = build_issue_architecture_context(_REAL_ISSUE, repo_root=REPO_ROOT)
    if graph is None:
        pytest.skip("issue not mapped to a wagon in this checkout's manifest")

    prompt = issue_review._render_prompt(
        issue_number=_REAL_ISSUE,
        dimensions=list(issue_review.DIMENSIONS),
        llm_id="claude-haiku",
        issue_body=body,
        graph_context=graph,
    )

    assert body[:200] in prompt, "the real issue body must be spliced in verbatim"
    assert "## Architecture context" in prompt, "the repo-graph summary must be inline"
    assert "ground your verdict" in prompt, (
        "the systemic dimension must be directed to consume the graph summary"
    )
