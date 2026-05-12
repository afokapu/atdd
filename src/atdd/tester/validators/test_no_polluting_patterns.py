# URN: test:integration-hardening:d002-meta-validator
# Acceptance: acc:integration-hardening:D002-UNIT-001-meta-validator-flags-bare-init-non-tmp
# Acceptance: acc:integration-hardening:D002-UNIT-002-meta-validator-flags-core-bare-config
# Acceptance: acc:integration-hardening:D002-UNIT-003-meta-validator-passes-properly-isolated-tests
# Acceptance: acc:integration-hardening:D002-INTEGRATION-001-scans-entire-repo-and-reports-violations
# WMBT: wmbt:integration-hardening:D002
# Phase: GREEN
# Layer: tester.validator

"""Meta-validator: AST-based structural detection of test-pollution patterns.

Scans test_*.py files for patterns that mutate shared git state outside
tmp_path scope — the contamination class behind Wave 12 (2026-05-12,
PRs #625/#627 each pushed 220,000-line deletions).

RED flags (validator FAILS the run):
  - subprocess.run(['git','init','--bare',...], cwd=os.getcwd())
      bare repo init with explicitly bad process-level cwd
  - subprocess.run(['git','config','core.bare','true']) with no -C flag
      and no cwd= keyword argument — fully unscoped core.bare mutation
  - subprocess.run(['git','config','core.bare','true'], cwd=os.getcwd())
      core.bare mutation with explicitly bad cwd

PASS (legitimate, properly isolated patterns):
  - subprocess.run(['git','-C',str(tmp_path),'config','core.bare','true'])
  - subprocess.run(['git','config','core.bare','true'], cwd=str(tmp_path))
  - subprocess.run(['git','config','--worktree','core.bare','true'])
  - subprocess.run(['git','init','--bare',str(tmp_path)])  # no bad cwd=
"""
from __future__ import annotations

import pytest

from atdd.coach.utils.repo import find_repo_root
from atdd.coach.utils.rule_binding import bind_rule
from atdd.tester.validators._no_polluting_patterns import (
    PollutionViolation,
    scan_repo,
    scan_text,
)
import atdd

from pathlib import Path


pytestmark = [pytest.mark.tester]

_RULE = bind_rule("tester.test-isolation.no-polluting-patterns")

REPO_ROOT = find_repo_root()
ATDD_PKG_DIR = Path(atdd.__file__).resolve().parent


# ---------------------------------------------------------------------------
# Fixture code snippets for unit tests
# ---------------------------------------------------------------------------

_BARE_INIT_BAD_CWD = """\
import subprocess
import os

def test_something():
    subprocess.run(["git", "init", "--bare", "/tmp/test"], cwd=os.getcwd())
"""

_BARE_INIT_BAD_CWD_PATH_CWD = """\
import subprocess
from pathlib import Path

def test_something():
    subprocess.run(["git", "init", "--bare", str(Path.cwd() / "repo")], cwd=Path.cwd())
"""

_CORE_BARE_NO_SCOPING = """\
import subprocess

def test_something(tmp_path):
    # BUG: no -C flag, no cwd= — bare mutation escapes tmp_path
    subprocess.run(["git", "config", "core.bare", "true"])
"""

_CORE_BARE_BAD_CWD = """\
import subprocess
import os

def test_something():
    subprocess.run(["git", "config", "core.bare", "true"], cwd=os.getcwd())
"""

# Clean / properly isolated fixtures — must produce zero violations
_CLEAN_BARE_INIT_TMP_ARG = """\
import subprocess

def test_something(tmp_path):
    subprocess.run(["git", "init", "--bare", str(tmp_path)], check=True)
"""

_CLEAN_CORE_BARE_C_FLAG = """\
import subprocess

def test_something(tmp_path):
    subprocess.run(
        ["git", "-C", str(tmp_path), "config", "core.bare", "true"],
        check=True,
    )
"""

_CLEAN_CORE_BARE_CWD_TMP = """\
import subprocess

def test_something(tmp_path):
    subprocess.run(
        ["git", "config", "core.bare", "true"],
        cwd=str(tmp_path),
        check=True,
    )
"""

_CLEAN_CORE_BARE_WORKTREE_FLAG = """\
import subprocess

def test_something():
    subprocess.run(
        ["git", "config", "--worktree", "core.bare", "true"],
        check=True,
    )
"""

_CLEAN_BARE_INIT_VIA_C_SUBDIR = """\
import subprocess

def test_something(tmp_path):
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", str(remote)], check=True, capture_output=True)
"""


# ---------------------------------------------------------------------------
# UNIT-001: bare-init with explicitly bad cwd is flagged
# ---------------------------------------------------------------------------


def test_flags_bare_init_with_getcwd_cwd():
    """D002-UNIT-001: scan_text flags subprocess.run bare-init with cwd=os.getcwd()."""
    violations = scan_text(_BARE_INIT_BAD_CWD)
    assert violations, (
        "scan_text() must return at least one PollutionViolation for a bare "
        "git-init call that passes cwd=os.getcwd().\n"
        "Pattern: subprocess.run(['git','init','--bare',...], cwd=os.getcwd())\n"
        "This is the contamination pattern that caused Wave 12 (2026-05-12)."
    )
    patterns = {v.pattern for v in violations}
    assert "bare-init-bad-cwd" in patterns, (
        f"Expected violation pattern 'bare-init-bad-cwd', got: {patterns}"
    )
    assert all(v.lineno > 0 for v in violations), (
        "All violations must report a non-zero lineno for pinpointing."
    )


def test_flags_bare_init_with_path_cwd():
    """D002-UNIT-001 (variant): scan_text flags bare-init with cwd=Path.cwd()."""
    violations = scan_text(_BARE_INIT_BAD_CWD_PATH_CWD)
    assert violations, (
        "scan_text() must return at least one violation for a bare git-init "
        "call that passes cwd=Path.cwd()."
    )
    patterns = {v.pattern for v in violations}
    assert "bare-init-bad-cwd" in patterns, f"Expected 'bare-init-bad-cwd', got: {patterns}"


# ---------------------------------------------------------------------------
# UNIT-002: core.bare config without any isolation is flagged
# ---------------------------------------------------------------------------


def test_flags_core_bare_no_scoping():
    """D002-UNIT-002: scan_text flags subprocess.run core.bare=true with no -C and no cwd=."""
    violations = scan_text(_CORE_BARE_NO_SCOPING)
    assert violations, (
        "scan_text() must return at least one PollutionViolation for a "
        "subprocess.run(['git','config','core.bare','true']) call with no "
        "-C flag and no cwd= keyword argument.\n"
        "Unscoped core.bare mutations are the root cause of Wave 12 contamination."
    )
    patterns = {v.pattern for v in violations}
    assert "core-bare-unscoped" in patterns, (
        f"Expected violation pattern 'core-bare-unscoped', got: {patterns}"
    )


def test_flags_core_bare_with_bad_cwd():
    """D002-UNIT-002 (variant): scan_text flags core.bare config with cwd=os.getcwd()."""
    violations = scan_text(_CORE_BARE_BAD_CWD)
    assert violations, (
        "scan_text() must return at least one violation for core.bare config "
        "with cwd=os.getcwd()."
    )
    patterns = {v.pattern for v in violations}
    assert "core-bare-unscoped" in patterns or "core-bare-bad-cwd" in patterns, (
        f"Expected 'core-bare-unscoped' or 'core-bare-bad-cwd', got: {patterns}"
    )


# ---------------------------------------------------------------------------
# UNIT-003: properly isolated patterns produce zero violations
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "code,label",
    [
        (_CLEAN_BARE_INIT_TMP_ARG, "bare-init with str(tmp_path) as path arg"),
        (_CLEAN_CORE_BARE_C_FLAG, "core.bare via -C str(tmp_path)"),
        (_CLEAN_CORE_BARE_CWD_TMP, "core.bare via cwd=str(tmp_path)"),
        (_CLEAN_CORE_BARE_WORKTREE_FLAG, "core.bare via --worktree flag"),
        (_CLEAN_BARE_INIT_VIA_C_SUBDIR, "bare-init via str(tmp_path subdir), no cwd="),
    ],
)
def test_clean_code_passes_without_violations(code: str, label: str):
    """D002-UNIT-003: properly isolated patterns produce zero violations (no false positives)."""
    violations = scan_text(code)
    assert not violations, (
        f"scan_text() must return zero violations for: {label!r}\n"
        f"Got violations:\n"
        + "\n".join(f"  [{v.lineno}] {v.pattern}: {v.detail}" for v in violations)
    )


def test_scan_text_handles_invalid_syntax_gracefully():
    """scan_text() returns empty list for code that cannot be parsed."""
    violations = scan_text("def broken(\n")
    assert violations == [], (
        "scan_text() must return [] for unparseable code — do not raise SyntaxError."
    )


# ---------------------------------------------------------------------------
# INTEGRATION-001: live repo scan finds zero violations
# ---------------------------------------------------------------------------


@pytest.mark.platform
def test_repo_has_no_pollution_patterns():
    """D002-INTEGRATION-001: scan_repo(ATDD_PKG_DIR) returns zero violations on the live repo.

    This is the structural gate: if any test file in src/atdd/ contains an
    unscoped core.bare mutation or a bare-init with explicitly bad cwd, this
    test fails with an actionable error message.

    Fix: scope the flagged git operation to tmp_path via -C or cwd= argument.
    See the fix_hint in src/atdd/tester/conventions/test-isolation.convention.yaml.
    """
    violations = scan_repo(ATDD_PKG_DIR)

    if not violations:
        return

    lines = [
        f"tester.test-isolation.no-polluting-patterns: {len(violations)} violation(s) found",
        "",
        "The following test files contain static pollution patterns that mutate",
        "shared git state outside tmp_path scope (Wave 12 contamination class):",
        "",
    ]
    for v in violations:
        lines.append(f"  [{v.file}:{v.lineno}] {v.pattern}: {v.detail}")

    lines += [
        "",
        "Fix: scope the git operation to tmp_path via -C or cwd= argument.",
        "See: src/atdd/tester/conventions/test-isolation.convention.yaml (fix_hint)",
        "Ref: Wave 12 contamination incident 2026-05-12, PRs #625/#627.",
    ]

    pytest.fail("\n".join(lines))
