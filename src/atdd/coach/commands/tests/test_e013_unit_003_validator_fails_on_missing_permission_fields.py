# URN: test:spawn-agents:spawn-time-non-interactive-convention:E013-UNIT-003-validator-fails-on-missing-permission-fields
# Acceptance: acc:spawn-agents:E013-UNIT-003-validator-fails-on-missing-permission-fields
"""E013-UNIT-003 — validator reports missing permission_flags or allowed_tools.

RED: no such validator exists yet.
GREEN: src/atdd/coach/validators/test_spawn_non_interactive_validator.py validates
every ADAPTER_REGISTRY entry has permission_flags and allowed_tools.
"""
import types
import pytest


def test_validator_module_exists():
    """The validator module must be importable before E013 is GREEN."""
    try:
        from atdd.coach.validators import test_spawn_non_interactive_validator  # noqa: F401
    except ImportError as exc:
        pytest.fail(
            f"src/atdd/coach/validators/test_spawn_non_interactive_validator.py does not exist "
            f"or is not importable: {exc}. E013 requires this validator."
        )


def test_validator_has_check_registry_function():
    from atdd.coach.validators import test_spawn_non_interactive_validator as v
    assert hasattr(v, "check_adapter_registry_fields"), (
        "test_spawn_non_interactive_validator must expose check_adapter_registry_fields() "
        "for E013 validation."
    )


def test_validator_detects_missing_permission_flags():
    from atdd.coach.validators import test_spawn_non_interactive_validator as v
    from atdd.coach.commands.spawn import AdapterConfig

    bad_entry = AdapterConfig(
        build_command=lambda p: "claude",
        permission_flags=[],
        allowed_tools=["Bash"],
        non_interactive_smoke=None,
    )
    violations = v.check_adapter_registry_fields({"codex": bad_entry})
    assert len(violations) >= 1, (
        "check_adapter_registry_fields should report a violation for an entry with "
        "empty permission_flags."
    )
    violation_text = " ".join(violations)
    assert "codex" in violation_text, (
        "Violation message must name the offending adapter key 'codex'."
    )


def test_validator_detects_missing_allowed_tools():
    from atdd.coach.validators import test_spawn_non_interactive_validator as v
    from atdd.coach.commands.spawn import AdapterConfig

    bad_entry = AdapterConfig(
        build_command=lambda p: "gemini",
        permission_flags=["--some-flag"],
        allowed_tools=[],
        non_interactive_smoke=None,
    )
    violations = v.check_adapter_registry_fields({"gemini": bad_entry})
    assert len(violations) >= 1, (
        "check_adapter_registry_fields should report a violation for an entry with "
        "empty allowed_tools."
    )
