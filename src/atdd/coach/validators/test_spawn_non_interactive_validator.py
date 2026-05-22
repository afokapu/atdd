# URN: component:spawn-agents:spawn-time-non-interactive-convention:spawn_non_interactive_validator:backend:application
# Runtime: python
# Purpose: Layer-B validator for spawn-time non-interactive contract (M002, issue #829).
"""Layer-B validator — spawn non-interactive contract (M002, issue #829).

Checks two classes of violation:
1. Raw multiplexer.send(ref, '/...') slash-command injection in observer rule files.
2. ADAPTER_REGISTRY entries missing permission_flags / allowed_tools, or declaring
   --permission-mode ask (which causes interactive modals).

Used by atdd validate coach to enforce the freedom-with-a-leash invariants.
"""
from __future__ import annotations

import ast
from pathlib import Path
from typing import TYPE_CHECKING, List, Optional

import pytest


if TYPE_CHECKING:
    from atdd.coach.commands.spawn import AdapterConfig


# ---------------------------------------------------------------------------
# check_observer_rules_no_slash_send
# ---------------------------------------------------------------------------

def check_observer_rules_no_slash_send(rule_files: List[Path]) -> List[str]:
    """AST-scan observer rule files for raw multiplexer.send('/...') calls.

    Returns a list of violation strings (one per offending call site).
    Empty list means the files are clean.
    """
    violations: List[str] = []
    for path in rule_files:
        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(path))
        except (OSError, SyntaxError) as exc:
            violations.append(f"{path}: parse error — {exc}")
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not (
                isinstance(func, ast.Attribute)
                and func.attr == "send"
                and len(node.args) >= 2
            ):
                continue
            second_arg = node.args[1]
            if _is_slash_string(second_arg):
                lineno = getattr(node, "lineno", "?")
                violations.append(
                    f"{path}:{lineno}: multiplexer.send slash-command injection detected "
                    f"(M002 Layer-B: use cli-return.jsonl instead of multiplexer.send('/...'))"
                )
    return violations


def _is_slash_string(node: ast.expr) -> bool:
    """Return True if node is a string literal starting with '/'."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value.startswith("/")
    if isinstance(node, ast.JoinedStr):
        parts = node.values
        if parts and isinstance(parts[0], ast.Constant):
            return str(parts[0].value).startswith("/")
    return False


# ---------------------------------------------------------------------------
# check_adapter_registry_fields
# ---------------------------------------------------------------------------

def check_adapter_registry_fields(registry: dict) -> List[str]:
    """Validate that every ADAPTER_REGISTRY entry has non-empty permission_flags
    and allowed_tools, and does not declare --permission-mode ask.

    Returns a list of violation strings. Empty list means registry is clean.
    """
    violations: List[str] = []
    for key, entry in registry.items():
        flags = getattr(entry, "permission_flags", None)
        tools = getattr(entry, "allowed_tools", None)
        if flags is None:
            violations.append(
                f"ADAPTER_REGISTRY[{key!r}]: missing permission_flags attribute "
                "(M002: add permission_flags to AdapterConfig)"
            )
        elif not isinstance(flags, list) or len(flags) == 0:
            violations.append(
                f"ADAPTER_REGISTRY[{key!r}]: permission_flags is empty or not a list "
                "(M002: must declare at least one permission flag)"
            )
        else:
            flags_str = " ".join(flags)
            if "--permission-mode ask" in flags_str:
                violations.append(
                    f"ADAPTER_REGISTRY[{key!r}]: permission_flags contains "
                    "'--permission-mode ask' which triggers interactive modals "
                    "(M002: use acceptEdits, not ask)"
                )
        if tools is None:
            violations.append(
                f"ADAPTER_REGISTRY[{key!r}]: missing allowed_tools attribute "
                "(M002: add allowed_tools to AdapterConfig)"
            )
        elif not isinstance(tools, list) or len(tools) == 0:
            violations.append(
                f"ADAPTER_REGISTRY[{key!r}]: allowed_tools is empty or not a list "
                "(M002: must declare at least one allowed tool)"
            )
    return violations


# ---------------------------------------------------------------------------
# Pytest test functions — run by atdd validate coach
# ---------------------------------------------------------------------------

def test_adapter_registry_fields_are_valid():
    from atdd.coach.commands.spawn import ADAPTER_REGISTRY
    violations = check_adapter_registry_fields(ADAPTER_REGISTRY)
    assert not violations, (
        "M002 Layer-B: ADAPTER_REGISTRY has non-interactive contract violations:\n"
        + "\n".join(f"  - {v}" for v in violations)
    )


def test_observer_rules_have_no_slash_send():
    observer_rules_dir = Path(__file__).parent.parent / "observer_rules"
    if not observer_rules_dir.is_dir():
        pytest.skip(f"observer_rules dir not found at {observer_rules_dir}")
    rule_files = [
        f for f in observer_rules_dir.glob("*.py")
        if not f.name.startswith("__")
    ]
    if not rule_files:
        pytest.skip("No observer rule files found to validate")
    violations = check_observer_rules_no_slash_send(rule_files)
    assert not violations, (
        "M002 Layer-B: observer rules contain slash-command injection violations:\n"
        + "\n".join(f"  - {v}" for v in violations)
    )
