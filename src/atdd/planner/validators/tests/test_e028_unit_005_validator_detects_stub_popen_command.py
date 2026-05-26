# URN: test:govern-lifecycle:smoke-false-green-prevention:E028-UNIT-005-validator-detects-stub-popen-command
# Acceptance: acc:govern-lifecycle:E028-UNIT-005-validator-detects-stub-popen-command
# WMBT: wmbt:govern-lifecycle:E028
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""
RED: scan_for_synthetic_fixture_bypass must emit one Violation with rule_id
'planner.smoke.synthetic-fixture-bypass' when the resolved SMOKE test runs
subprocess.Popen with a cat/sleep/python stub command.  Currently fails because
src/atdd/planner/validators/test_smoke_synthetic_fixture_bypass.py does not
exist yet.
"""
from __future__ import annotations

import textwrap

import pytest
import yaml

from atdd.coach.utils.repo import find_repo_root

pytestmark = [pytest.mark.planner]


def test_validator_detects_stub_popen_cat(tmp_path):
    """Validator emits one violation when the SMOKE test launches subprocess.Popen(['cat', ...])."""
    from atdd.planner.validators.test_smoke_synthetic_fixture_bypass import (
        scan_for_synthetic_fixture_bypass,
    )

    test_file = tmp_path / "test_stub_popen_smoke.py"
    test_file.write_text(
        textwrap.dedent(
            """\
            import subprocess
            import pytest

            pytestmark = [pytest.mark.smoke, pytest.mark.platform]

            def test_example(tmp_path):
                proc = subprocess.Popen(["cat", "/dev/null"], stdout=subprocess.PIPE)
                assert proc.wait() == 0
            """
        )
    )

    wmbt_yaml = tmp_path / "E999.yaml"
    wmbt_yaml.write_text(
        yaml.dump(
            {
                "urn": "wmbt:test-wagon:E999",
                "acceptances": [
                    {
                        "identity": {
                            "urn": "acc:test-wagon:E999-SMOKE-001-example",
                            "id": "AC-SMOKE-001",
                            "phase": "SMOKE",
                        },
                        "harness": {"type": "smoke", "category": "backend"},
                        "given": {"abstract": ["test env"]},
                        "when": {"abstract": "test runs"},
                        "then": {"abstract": ["passes"]},
                    }
                ],
            }
        )
    )

    violations = scan_for_synthetic_fixture_bypass(
        wmbt_files=[wmbt_yaml],
        repo_root=tmp_path,
        resolve_test_file=lambda _urn: test_file,
    )

    assert len(violations) == 1, (
        f"Expected exactly 1 violation for Popen(['cat',...]) stub, got {len(violations)}: "
        f"{violations}"
    )
    v = violations[0]
    assert v.rule_id == "planner.smoke.synthetic-fixture-bypass", (
        f"Expected rule_id 'planner.smoke.synthetic-fixture-bypass', got {v.rule_id!r}"
    )
    assert any(stub in v.detail for stub in ("cat", "sleep", "python")), (
        f"Expected stub command name in violation detail, got: {v.detail!r}"
    )
