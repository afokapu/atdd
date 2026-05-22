# URN: test:spawn-agents:spawn-time-non-interactive-convention:M001-SMOKE-001-live-session-naming-apply-has-no-slash-rename
# Acceptance: acc:spawn-agents:M001-SMOKE-001-live-session-naming-apply-has-no-slash-rename
# WMBT: wmbt:spawn-agents:M001
# Phase: SMOKE
# Layer: smoke
# Runtime: python
# Assertion: behavioral
"""M001-SMOKE-001 — the deployed session_naming_apply.py source contains no
paste_text or send call whose text argument starts with '/rename'.

SMOKE: AST-scans the real source file on disk (not a synthetic fixture).
"""
from __future__ import annotations

import ast
import inspect

import pytest


@pytest.mark.smoke
def test_live_session_naming_apply_has_no_slash_rename():
    from atdd.coach.utils import session_naming_apply

    source = inspect.getsource(session_naming_apply)
    tree = ast.parse(source)

    violations = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute):
            continue
        if func.attr not in ("paste_text", "send"):
            continue
        if len(node.args) < 2:
            continue
        arg = node.args[1]
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            if arg.value.startswith("/rename"):
                violations.append(f"line {node.lineno}: {func.attr}(ref, {arg.value!r})")
        elif isinstance(arg, ast.JoinedStr):
            parts = arg.values
            if parts and isinstance(parts[0], ast.Constant):
                if str(parts[0].value).startswith("/rename"):
                    violations.append(f"line {node.lineno}: {func.attr}(ref, f-string starting '/rename')")

    assert not violations, (
        "M001-SMOKE-001: live session_naming_apply.py still contains '/rename' "
        "injection calls. M001 removal not applied:\n"
        + "\n".join(f"  {v}" for v in violations)
    )
