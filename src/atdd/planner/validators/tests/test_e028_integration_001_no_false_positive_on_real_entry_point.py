# URN: test:govern-lifecycle:smoke-false-green-prevention:E028-INTEGRATION-001-no-false-positive-on-real-entry-point
# Acceptance: acc:govern-lifecycle:E028-INTEGRATION-001-no-false-positive-on-real-entry-point
# WMBT: wmbt:govern-lifecycle:E028
# Phase: GREEN
# Layer: integration
# Assertion: behavioral
"""
GREEN: scan_for_synthetic_fixture_bypass must return an empty violation list
when the SMOKE test uses subprocess.run(['atdd', 'spawn', ...]) with no
FakeMultiplexer import and no stub Popen command.
"""
from __future__ import annotations

import textwrap

import pytest
import yaml

pytestmark = [pytest.mark.planner]


def test_no_false_positive_on_real_entry_point(tmp_path):
    """Validator emits no violations for a SMOKE test that drives atdd spawn."""
    from atdd.planner.validators._meta_walker import (
        scan_for_synthetic_fixture_bypass,
    )

    test_file = tmp_path / "test_real_spawn_smoke.py"
    test_file.write_text(
        textwrap.dedent(
            """\
            import subprocess
            import sys
            import pytest

            pytestmark = [pytest.mark.smoke, pytest.mark.platform]

            def invoke_atdd_spawn(agent_id, runtime_dir, adapter_command):
                \"\"\"Real atdd spawn path via the atdd CLI.\"\"\"
                return subprocess.Popen(
                    [sys.executable, "-m", "atdd.cli", "spawn",
                     "--agent-id", agent_id,
                     "--runtime-dir", str(runtime_dir),
                     "--",
                     *adapter_command],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )

            def test_example(tmp_path):
                proc = invoke_atdd_spawn(
                    "test-agent",
                    tmp_path,
                    [sys.executable, "-c", "print('hello')"],
                )
                proc.wait(timeout=10)
                assert proc.returncode == 0
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
                            "urn": "acc:test-wagon:E999-SMOKE-001-real-spawn",
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

    assert violations == [], (
        f"Expected no violations for real-entry-point SMOKE test, got {len(violations)}:\n"
        + "\n".join(f"  {v}" for v in violations)
    )
