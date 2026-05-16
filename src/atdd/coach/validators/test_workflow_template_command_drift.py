# URN: component:govern-lifecycle:enforcement-substrate:test_workflow_template_command_drift:backend:domain
# Runtime: python
# Purpose: Lock the contract that every `run: atdd ...` line ProjectInitializer writes into consumer workflows resolves to a real subcommand and parses cleanly under the live argparse (flag- and subcommand-level drift, #473 + #481).

"""Drift guard for `atdd init` workflow templates vs. the live CLI.

Two drift classes, two issues:

#473 — flag-level drift. The 3.10.0 release dropped `-m FLAG` from
``atdd validate``, but ``ProjectInitializer._write_workflow`` and
``_write_infra_workflow`` kept emitting ``atdd validate coach -m "not
github_api"`` into every consumer's ``.github/workflows/atdd-validate*.yml``.
Every consumer who ran ``atdd init --force`` after the upgrade hit
``unrecognized arguments: -m`` on first push.

#481 — subcommand-level drift. The initializer also emitted
``atdd baseline update`` into the (now-retired) ``baseline-sync`` job;
``baseline`` is not a top-level subcommand, so argparse rejects it with
``invalid choice`` — a different failure token #473's guard never matched.
This validator now flags BOTH classes across EVERY emitted ``run: atdd
...`` line, not just ``atdd validate ...`` lines.

It writes the workflow templates into a tmp directory via the real
initializer, extracts every emitted ``run: atdd ...`` literal back out,
and feeds each through the live argparse via subprocess. ``--diagnostics-only``
is appended to short-circuit after parse on ``atdd validate ...`` lines —
argparse failures still surface as rc=2 + (``unrecognized arguments`` |
``invalid choice``), so a parse miss is unambiguous.

Conventions: ``src/atdd/coach/conventions/rule-id.convention.yaml``
             (rules ``coach.initializer.template-cli-drift`` and
             ``coach.workflow-template.command-must-parse``).
"""

from __future__ import annotations

import re
import shlex
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Tuple

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

# #481: subcommand-level drift guard. #473's `_RULE` caught flag drift
# (`unrecognized arguments`) on `atdd validate ...` lines; this rule widens
# the guard to EVERY `run: atdd ...` line and to `invalid choice` failures
# (a non-existent subcommand, e.g. the stranded `atdd baseline update`).
_COMMAND_RULE = bind_rule("coach.workflow-template.command-must-parse")

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
    """Pull every `run: atdd ...` literal out of a generated workflow YAML.

    Thin convenience wrapper over :func:`extract_atdd_invocations` — kept as
    the file-path-oriented entry point; both share one parsing source.
    """
    return [inv.raw for inv in extract_atdd_invocations(workflow_path.read_text())]


@dataclass(frozen=True)
class AtddInvocation:
    """One `run: atdd ...` line, decomposed for subcommand-level drift checks.

    Attributes:
        subcommand: The first token after ``atdd`` (e.g. ``validate``,
            ``auto-phase``, ``baseline``).
        args: Every token after the subcommand.
        raw: The full ``atdd ...`` literal as emitted.
    """

    subcommand: str
    args: List[str] = field(default_factory=list)
    raw: str = ""


def extract_atdd_invocations(template_text: str) -> List[AtddInvocation]:
    """Capture every `run: atdd ...` line in a workflow template (#481).

    Unlike #473's validate-only framing, this captures EVERY ``run: atdd
    <subcommand> ...`` line — validate and non-validate alike — as a
    structured record. Non-atdd ``run:`` lines never match ``_RUN_LINE_RE``
    (which anchors on ``atdd``), so they are excluded by construction.
    """
    invocations: List[AtddInvocation] = []
    for match in _RUN_LINE_RE.finditer(template_text):
        cmd = match.group(1).strip()
        tokens = shlex.split(cmd)
        if len(tokens) < 2 or tokens[0] != "atdd":
            continue
        invocations.append(
            AtddInvocation(subcommand=tokens[1], args=tokens[2:], raw=cmd)
        )
    return invocations


# ---------------------------------------------------------------------------
# Live-argparse parse check
# ---------------------------------------------------------------------------
_PARSE_FAIL_RC = 2
_UNRECOGNIZED_TOKEN = "unrecognized arguments"
# #481: a non-existent SUBCOMMAND fails argparse with `invalid choice`,
# not `unrecognized arguments` — the blind spot that let `atdd baseline
# update` reach consumers despite #473's drift guard.
_INVALID_CHOICE_TOKEN = "invalid choice"


def _is_parse_failure(result: subprocess.CompletedProcess) -> bool:
    """True when the live argparse rejected the command outright.

    Covers both drift classes: a rejected flag (``unrecognized
    arguments``) and a non-existent subcommand (``invalid choice``).
    """
    if result.returncode != _PARSE_FAIL_RC:
        return False
    return (
        _UNRECOGNIZED_TOKEN in result.stderr
        or _INVALID_CHOICE_TOKEN in result.stderr
    )


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
def evaluate_template_command_drift(
    templates: List[Tuple[Path, str]]
) -> List[Violation]:
    """Pure evaluator: flag every `run: atdd ...` line that fails live argparse.

    Args:
        templates: ``[(workflow_path, template_text), ...]`` pairs. The path
            is used only for Violation location/detail; the text is scanned.

    Returns:
        One Violation per emitted ``run: atdd ...`` line whose subcommand
        the live CLI does not declare (``invalid choice``) or whose flags
        the subparser rejects (``unrecognized arguments``). Lines that
        parse cleanly produce nothing.
    """
    violations: List[Violation] = []
    for path, text in templates:
        # Pre-compute line offsets for line-number reporting.
        lineno_by_cmd = {}
        for match in _RUN_LINE_RE.finditer(text):
            lineno_by_cmd[match.group(1).strip()] = (
                text[: match.start()].count("\n") + 1
            )
        for inv in extract_atdd_invocations(text):
            result = _parse_under_live_cli(inv.raw)
            if not _is_parse_failure(result):
                continue
            last = result.stderr.strip().splitlines()[-1]
            violations.append(
                Violation(
                    rule_id=_COMMAND_RULE.rule_id,
                    severity=_COMMAND_RULE.severity,
                    location=f"{path}:{lineno_by_cmd.get(inv.raw, '?')}",
                    detail=(
                        f"emitted run-line {inv.raw!r} fails the live "
                        f"argparse: {last}"
                    ),
                    fix_hint_ref=getattr(_COMMAND_RULE, "fix_hint_ref", None),
                )
            )
    return violations


def scan_workflow_dir_for_command_drift(workflows_dir: Path) -> List[Violation]:
    """Scan every `*.yml` workflow file in a directory for CLI command drift.

    The directory-level entry point the coach suite runs over real-emitted
    workflow files: it reads each workflow YAML and delegates to
    :func:`evaluate_template_command_drift`.
    """
    workflows_dir = Path(workflows_dir)
    templates: List[Tuple[Path, str]] = []
    for workflow_path in sorted(workflows_dir.glob("*.yml")):
        templates.append((workflow_path, workflow_path.read_text()))
    return evaluate_template_command_drift(templates)


def scan_workflow_templates_for_cli_drift() -> List[Violation]:
    """Return Violations for every emitted run-line that fails live argparse.

    Drives the real ``ProjectInitializer`` emit into a tmp directory, then
    scans every emitted workflow file — validate AND non-validate lines
    alike (#481 widened #473's validate-only scope).
    """
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp)
        _emit_workflow_files(target)
        return scan_workflow_dir_for_command_drift(
            target / ".github" / "workflows"
        )


# ===========================================================================
# Test
# ===========================================================================
@pytest.mark.coach
def test_every_run_line_parses_under_live_cli():
    """Every `run: atdd ...` line the initializer emits parses under live argparse.

    SPEC: ``rule-id.convention.yaml::rules[coach.initializer.template-cli-drift,
          coach.workflow-template.command-must-parse]``.

    Given:  Workflow YAMLs written by ``ProjectInitializer._write_workflow``
            and ``_write_infra_workflow`` against a tmp target directory.
    When:   Every emitted ``run: atdd ...`` line — validate AND non-validate
            alike — is fed through the live ``python -m atdd`` argparse via
            subprocess.
    Then:   No command produces ``rc=2`` + (``unrecognized arguments`` |
            ``invalid choice``) — the templates and the CLI are in sync at
            both flag and subcommand level.
    """
    violations = scan_workflow_templates_for_cli_drift()
    assert_disposition_satisfied(
        validator_id="workflow_template_command_drift",
        violations=violations,
    )
