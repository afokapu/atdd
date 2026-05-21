# URN: test:spawn-agents:spawn-time-non-interactive-convention:M002-UNIT-001-validator-detects-slash-send-in-observer-rules
# URN: test:spawn-agents:spawn-time-non-interactive-convention:M002-UNIT-002-validator-detects-permission-mode-ask-in-adapter
# URN: test:spawn-agents:spawn-time-non-interactive-convention:M002-UNIT-003-current-observer-rules-pass-validator
# Acceptance: acc:spawn-agents:M002-UNIT-001-validator-detects-slash-send-in-observer-rules
# Acceptance: acc:spawn-agents:M002-UNIT-002-validator-detects-permission-mode-ask-in-adapter
# Acceptance: acc:spawn-agents:M002-UNIT-003-current-observer-rules-pass-validator
"""M002 Layer-B validator tests — spawn non-interactive contract enforcement.

RED: test_spawn_non_interactive_validator.py does not exist yet.
GREEN: the module is created with check_adapter_registry_fields() and
check_observer_rules_no_slash_send() functions.
"""
import ast
import textwrap
from pathlib import Path
import pytest


# ---------------------------------------------------------------------------
# Validator import guard — the module must exist for any test to pass
# ---------------------------------------------------------------------------

def _import_validator():
    try:
        from atdd.coach.validators import test_spawn_non_interactive_validator as v
        return v
    except ImportError as exc:
        pytest.fail(
            f"src/atdd/coach/validators/test_spawn_non_interactive_validator.py missing. "
            f"M002: create this validator module. Error: {exc}"
        )


# ---------------------------------------------------------------------------
# M002-UNIT-001: validator detects slash-command send in observer rules
# ---------------------------------------------------------------------------

def test_validator_detects_slash_send_in_observer_rule(tmp_path):
    v = _import_validator()
    observer_file = tmp_path / "bad_observer_rule.py"
    observer_file.write_text(
        textwrap.dedent("""\
            def apply_correction(multiplexer, ref, text):
                multiplexer.send(ref, '/rename bad_name')
        """)
    )
    violations = v.check_observer_rules_no_slash_send([observer_file])
    assert len(violations) >= 1, (
        "check_observer_rules_no_slash_send must detect multiplexer.send('/...') in observer "
        "rule files. M002 Layer-B: slash-command injection via multiplexer.send is forbidden."
    )
    violation_text = " ".join(violations)
    assert str(observer_file) in violation_text or "bad_observer_rule" in violation_text, (
        f"Violation message must reference the offending file. Got: {violations}"
    )


def test_validator_does_not_flag_cli_return_send(tmp_path):
    v = _import_validator()
    clean_file = tmp_path / "clean_observer_rule.py"
    clean_file.write_text(
        textwrap.dedent("""\
            def apply_correction(agent_id, runtime):
                # writes to cli-return.jsonl, not multiplexer
                import json
                record = {'action': 'approve'}
                with open(runtime / agent_id / 'cli-return.jsonl', 'a') as f:
                    f.write(json.dumps(record) + '\\n')
        """)
    )
    violations = v.check_observer_rules_no_slash_send([clean_file])
    assert not violations, (
        f"check_observer_rules_no_slash_send incorrectly flagged a clean observer rule. "
        f"Violations: {violations}"
    )


# ---------------------------------------------------------------------------
# M002-UNIT-002: validator detects --permission-mode ask in adapter config
# ---------------------------------------------------------------------------

def test_validator_detects_permission_mode_ask_in_adapter():
    v = _import_validator()
    from atdd.coach.commands.spawn import AdapterConfig

    bad_entry = AdapterConfig(
        build_command=lambda p: "claude --permission-mode ask",
        permission_flags=["--permission-mode", "ask"],
        allowed_tools=["Bash"],
        non_interactive_smoke=None,
    )
    violations = v.check_adapter_registry_fields({"claude-code": bad_entry})
    assert len(violations) >= 1, (
        "check_adapter_registry_fields must detect '--permission-mode ask' as a violation. "
        "M002: adapters must not request interactive permission prompts."
    )
    violation_text = " ".join(violations)
    assert "--permission-mode ask" in violation_text or "ask" in violation_text, (
        f"Violation must reference '--permission-mode ask'. Got: {violations}"
    )


# ---------------------------------------------------------------------------
# M002-UNIT-003: current observer rules pass with zero violations
# ---------------------------------------------------------------------------

def test_current_observer_rules_have_no_slash_send_violations():
    v = _import_validator()
    observer_rules_dir = Path("src/atdd/coach/observer_rules")
    if not observer_rules_dir.is_dir():
        pytest.skip("observer_rules dir not found — skipping filesystem scan")
    rule_files = list(observer_rules_dir.glob("*.py"))
    assert rule_files, "No observer rule .py files found to validate"
    violations = v.check_observer_rules_no_slash_send(rule_files)
    assert not violations, (
        f"Current observer rules contain slash-send violations after E014 fix. "
        f"M002 Layer-B: all observer rules must use cli-return, not multiplexer.send('/...'). "
        f"Violations: {violations}"
    )
