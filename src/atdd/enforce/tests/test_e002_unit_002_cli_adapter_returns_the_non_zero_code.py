# URN: test:enforce-conventions-ci:E002-UNIT-002-cli-adapter-returns-the-non-zero-code
# Acceptance: acc:enforce-conventions-ci:E002-UNIT-002-cli-adapter-returns-the-non-zero-code
# WMBT: wmbt:enforce-conventions-ci:E002
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""GREEN Test for acc:enforce-conventions-ci:E002-UNIT-002-cli-adapter-returns-the-non-zero-code.

PINS the seam between the verdict and the shell: the ``atdd enforce`` CLI adapter
hands the runner's non-zero exit code BACK (``atdd.cli`` does ``sys.exit(run(...))``),
rather than absorbing it and returning 0. CI gates on exactly this integer.

Driven over a REAL substrate built by the shared conftest builder — a real vendored
provider CLI subprocessed by the real runner over a real bound STRICT convention —
so the adapter is proven against the real verdict, not a stubbed one.
"""
from __future__ import annotations

from pathlib import Path

from atdd.enforce.cli import run

from .conftest import build_content_sensitive_substrate


def test_adapter_returns_one_when_a_strict_rule_fails(tmp_path: Path, capsys) -> None:
    root = build_content_sensitive_substrate(tmp_path)

    # dirty/ holds a file the real provider genuinely finds a violation in -> the
    # bound STRICT rule acme.rule.owned fails -> the adapter must hand back 1.
    code = run(["--repo-root", str(root), "--paths", "dirty"])

    assert code == 1, "the CLI adapter absorbed a strict FAIL — a blocking gate would go green"

    out = capsys.readouterr().out
    # The failure is never silent: the report is printed and names the failing rule.
    assert "acme.rule.owned" in out
    assert "FAIL" in out


def test_adapter_returns_zero_when_nothing_fails(tmp_path: Path, capsys) -> None:
    root = build_content_sensitive_substrate(tmp_path)

    # clean/ holds a file the SAME real provider finds nothing in — so this proves
    # the gate is not simply always-red: a clean tree really does exit 0.
    code = run(["--repo-root", str(root), "--paths", "clean"])

    assert code == 0

    out = capsys.readouterr().out
    assert "PASS" in out
