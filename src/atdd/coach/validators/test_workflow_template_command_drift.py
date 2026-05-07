# URN: component:govern-lifecycle:enforcement-substrate:test_workflow_template_command_drift:backend:domain
# Runtime: python
# Purpose: Lock the contract that every `run: atdd ...` line ProjectInitializer writes into consumer workflows parses cleanly under the live argparse.

"""Drift guard for `atdd init` workflow templates vs. the live CLI (issue #473).

The 3.10.0 release dropped `-m FLAG` from `atdd validate`, but
``ProjectInitializer._write_workflow`` and ``_write_infra_workflow`` kept
emitting ``atdd validate coach -m "not github_api"`` and
``atdd validate coach -m github_api`` into every consumer's
``.github/workflows/atdd-validate*.yml``. Every consumer who ran
``atdd init --force`` after the upgrade hit ``unrecognized arguments: -m``
on first push — a required CI gate failing on a hardcoded template,
before any actual validators ran.

This validator closes that drift class. It writes the workflow templates
into a tmp directory via the real initializer, greps every emitted
``run: atdd ...`` literal back out, and feeds each through the live
argparse via subprocess. ``--diagnostics-only`` is appended to short-circuit
after parse — argparse failures still surface as rc=2 + ``unrecognized
arguments``, so a parse miss is unambiguous.

Convention: ``src/atdd/coach/conventions/rule-id.convention.yaml``
            (rule ``coach.initializer.template-cli-drift``).
"""

from __future__ import annotations

import re
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List

import pytest
import yaml

import atdd
from atdd.coach.commands.initializer import ProjectInitializer
from atdd.coach.utils.disposition_gate import assert_disposition_satisfied
from atdd.coach.utils.rule_binding import bind_rule
from atdd.coach.validators._violation import Violation


# ---------------------------------------------------------------------------
# Path constants & rule binding
# ---------------------------------------------------------------------------
ATDD_PKG_DIR = Path(atdd.__file__).resolve().parent
REPO_ROOT = ATDD_PKG_DIR.parent.parent

_RULE = bind_rule("coach.initializer.template-cli-drift")

# Match `run: atdd ...` lines (in YAML scalar form) regardless of indentation
# or trailing comments. Captures the bash command literal that follows `run:`.
_RUN_LINE_RE = re.compile(r"^\s*run:\s*(atdd\s+\S.*?)$", re.MULTILINE)


# ---------------------------------------------------------------------------
# Template emission
# ---------------------------------------------------------------------------
def _emit_workflow_files(target_dir: Path) -> List[Path]:
    """Drive both workflow writers and return the generated YAML paths.

    Uses the real ``ProjectInitializer`` against ``target_dir`` (a tmp
    location), so this validator measures what consumers actually receive
    when they run ``atdd init --force``, not a static read of source.
    """
    cfg_dir = target_dir / ".atdd"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    (cfg_dir / "config.yaml").write_text(
        yaml.safe_dump({"github": {"repo": "owner/repo"}})
    )
    init = ProjectInitializer(target_dir=target_dir)
    init._write_workflow(repo="owner/repo")
    init._write_infra_workflow()
    return sorted((target_dir / ".github" / "workflows").glob("*.yml"))


def _extract_atdd_run_lines(workflow_path: Path) -> List[str]:
    """Pull every `run: atdd ...` literal out of a generated workflow YAML."""
    text = workflow_path.read_text()
    return [m.group(1).strip() for m in _RUN_LINE_RE.finditer(text)]


# ---------------------------------------------------------------------------
# Live-argparse parse check
# ---------------------------------------------------------------------------
_PARSE_FAIL_RC = 2
_UNRECOGNIZED_TOKEN = "unrecognized arguments"


def _parse_under_live_cli(cmd: str) -> subprocess.CompletedProcess:
    """Feed ``cmd`` through the live atdd argparse via subprocess.

    ``--diagnostics-only`` is appended ONLY for ``atdd validate ...`` lines:
    those carry the flag and short-circuit after argparse succeeds. Other
    ``atdd ...`` commands (e.g. ``atdd baseline update``) are passed
    through as-is — argparse failures still fail fast at rc=2, and we
    treat any non-2 rc as parse-success regardless of the rest of the
    command's behavior.
    """
    tokens = shlex.split(cmd)
    assert tokens and tokens[0] == "atdd", f"expected `atdd ...` shape: {cmd!r}"
    args = tokens[1:]
    if args[:1] == ["validate"]:
        args = args + ["--diagnostics-only"]
    return subprocess.run(
        [sys.executable, "-m", "atdd"] + args,
        capture_output=True,
        text=True,
        timeout=30,
        cwd=REPO_ROOT,
    )


# ---------------------------------------------------------------------------
# Scanner
# ---------------------------------------------------------------------------
def scan_workflow_templates_for_cli_drift() -> List[Violation]:
    """Return Violations for every emitted run-line that fails live argparse."""
    violations: List[Violation] = []
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp)
        for workflow_path in _emit_workflow_files(target):
            rel_workflow = workflow_path.relative_to(target)
            text = workflow_path.read_text()
            # Pre-compute line offsets for line-number reporting.
            lineno_by_match = {}
            for match in _RUN_LINE_RE.finditer(text):
                lineno_by_match[match.group(1).strip()] = (
                    text[: match.start()].count("\n") + 1
                )

            for cmd in _extract_atdd_run_lines(workflow_path):
                result = _parse_under_live_cli(cmd)
                if (
                    result.returncode == _PARSE_FAIL_RC
                    and _UNRECOGNIZED_TOKEN in result.stderr
                ):
                    last = result.stderr.strip().splitlines()[-1]
                    violations.append(
                        Violation(
                            rule_id=_RULE.rule_id,
                            severity=_RULE.severity,
                            location=(
                                f"src/atdd/coach/commands/initializer.py "
                                f"(emit → {rel_workflow}:"
                                f"{lineno_by_match.get(cmd, '?')})"
                            ),
                            detail=(
                                f"emitted run-line {cmd!r} fails the live "
                                f"argparse: {last}"
                            ),
                            fix_hint_ref=getattr(_RULE, "fix_hint_ref", None),
                        )
                    )
    return violations


# ===========================================================================
# Test
# ===========================================================================
@pytest.mark.coach
def test_every_run_line_parses_under_live_cli():
    """Every `run: atdd ...` line the initializer emits parses under live argparse.

    SPEC: ``rule-id.convention.yaml::rules[coach.initializer.template-cli-drift]``.

    Given:  Workflow YAMLs written by ``ProjectInitializer._write_workflow``
            and ``_write_infra_workflow`` against a tmp target directory.
    When:   Every emitted ``run: atdd ...`` line is fed through the live
            ``python -m atdd`` argparse via subprocess.
    Then:   No command produces ``rc=2`` + ``unrecognized arguments`` —
            the templates and the CLI are in sync.
    """
    violations = scan_workflow_templates_for_cli_drift()
    assert_disposition_satisfied(
        validator_id="workflow_template_command_drift",
        violations=violations,
    )
