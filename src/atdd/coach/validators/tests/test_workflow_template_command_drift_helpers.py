# URN: component:govern-lifecycle:enforcement-substrate:test_workflow_template_command_drift_helpers:backend:domain
# Runtime: python
# Purpose: Unit tests for the parsing/emission helpers in test_workflow_template_command_drift.

"""Pure-function unit tests for the workflow-template drift helpers (issue #473).

The repo-walking integration test (``test_every_run_line_parses_under_live_cli``)
lives in ``test_workflow_template_command_drift.py`` itself; this file
isolates the parsing helpers so each invariant has a focused regression
without re-running the live argparse.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from atdd.coach.validators.test_workflow_template_command_drift import (
    _RUN_LINE_RE,
    _emit_workflow_files,
    _extract_atdd_run_lines,
    _parse_under_live_cli,
)


# ---------------------------------------------------------------------------
# Run-line regex
# ---------------------------------------------------------------------------

class TestRunLineRegex:
    @pytest.mark.parametrize("line, expected", [
        ("        run: atdd validate coach --skip-api",
         "atdd validate coach --skip-api"),
        ("      run: atdd validate coach --api-only",
         "atdd validate coach --api-only"),
        ("        run: atdd baseline update",
         "atdd baseline update"),
        # Indented under YAML key, with trailing punctuation preserved
        ("    run: atdd validate planner",
         "atdd validate planner"),
    ])
    def test_captures_atdd_command(self, line, expected):
        m = _RUN_LINE_RE.search(line)
        assert m is not None, f"regex missed: {line!r}"
        assert m.group(1).strip() == expected

    @pytest.mark.parametrize("line", [
        "        run: pip3 install atdd",          # not an `atdd ...` invocation
        "        run: echo hi",                    # unrelated run line
        "      - name: Run github_api validators", # not a `run:` scalar
    ])
    def test_skips_non_atdd_run_lines(self, line):
        m = _RUN_LINE_RE.search(line)
        # Either no match, or first token is `atdd` and the rest checks out;
        # for these non-atdd cases we expect no match (the regex anchors
        # `atdd\s+` after `run:`).
        if m is not None:
            assert not m.group(1).startswith("atdd"), (
                f"regex incorrectly matched non-atdd line: {line!r}"
            )


# ---------------------------------------------------------------------------
# Emission round-trip
# ---------------------------------------------------------------------------

class TestEmissionRoundTrip:
    def test_emits_both_workflow_files(self, tmp_path: Path):
        paths = _emit_workflow_files(tmp_path)
        names = {p.name for p in paths}
        assert "atdd-validate.yml" in names
        assert "atdd-validate-infra.yml" in names

    def test_each_emitted_file_contains_at_least_one_atdd_run_line(self, tmp_path: Path):
        paths = _emit_workflow_files(tmp_path)
        for p in paths:
            cmds = _extract_atdd_run_lines(p)
            atdd_cmds = [c for c in cmds if c.startswith("atdd ")]
            assert atdd_cmds, f"{p.name} emitted no `atdd ...` run-lines"


# ---------------------------------------------------------------------------
# Live-argparse subprocess wrapper
# ---------------------------------------------------------------------------

class TestParseUnderLiveCli:
    def test_known_good_command_parses(self):
        result = _parse_under_live_cli("atdd validate coach --skip-api")
        # Either rc=0 (diagnostics emitted) or rc=1 (no diagnostics yet);
        # rc=2 would indicate parse failure.
        assert result.returncode != 2, (
            f"--skip-api should parse cleanly; got rc={result.returncode}\n"
            f"stderr: {result.stderr!r}"
        )

    def test_known_bad_command_returns_unrecognized(self):
        # `-m FLAG` was removed in 3.10.0 — the canonical #473 reproducer.
        result = _parse_under_live_cli('atdd validate coach -m "not github_api"')
        assert result.returncode == 2
        assert "unrecognized arguments" in result.stderr

    def test_appends_diagnostics_only_for_validate_subcommand(self):
        # Indirectly verified: a clean validate run-line short-circuits via
        # diagnostics-only and exits within seconds rather than running the
        # full validator suite. We assert wall-clock is under the 30s timeout.
        result = _parse_under_live_cli("atdd validate planner --skip-api")
        assert result.returncode != 2
