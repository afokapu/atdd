# URN: test:dispatch-validators:dispatch-tier-one-validators:E001-SMOKE-001-violation-collector-real-subprocess
# Acceptance: acc:dispatch-validators:E001-UNIT-001-pytest-plugin-captures-all-violations
# WMBT: wmbt:dispatch-validators:E001
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""SMOKE — end-to-end coach dispatcher → pytest subprocess → violations.jsonl.

Spawns a real ``python -m pytest`` subprocess via
``atdd.coach.runtime.dispatcher.dispatch_validators`` against a fixture
validator that emits a known mix of Violations through
``assert_disposition_satisfied``. Asserts:

* The plugin loads under ``PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`` via
  ``-p atdd.coach.plugins.violation_collector`` (validator-invocation.md §2).
* Every emitted Violation appears as one record in
  ``<runtime>/validations/<sha>/violations.jsonl``.
* Each line validates against ``validator-result.schema.json``.
"""
from __future__ import annotations

import json
import os
import sys
import textwrap
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

import atdd

ATDD_PKG_DIR = Path(atdd.__file__).resolve().parent
VALIDATOR_RESULT_SCHEMA = (
    ATDD_PKG_DIR / "coach" / "schemas" / "validator-result.schema.json"
)


def _validator_schema() -> Draft202012Validator:
    return Draft202012Validator(json.loads(VALIDATOR_RESULT_SCHEMA.read_text()))


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _worktree_src() -> Path:
    """Resolve this worktree's ``src/`` so the subprocess can import the
    locally-edited ``atdd.coach.plugins.violation_collector`` module
    (otherwise pytest's autoload-disabled subprocess would only see the
    site-installed package)."""
    return Path(__file__).resolve().parents[4]


def test_dispatcher_runs_real_pytest_with_collector_plugin(tmp_path, monkeypatch):
    """Drive coach.runtime.dispatcher against a fixture validator file."""
    from atdd.coach.runtime.dispatcher import dispatch_validators

    # Build a self-contained worktree-like environment: a pyproject so the
    # subprocess pytest pins ``rootdir``, and a fixture validator that
    # exercises strict + advisory + suppressed dispositions through the
    # disposition gate.
    workspace = tmp_path / "wt"
    workspace.mkdir()

    # The fixture target file the validator will reference.
    target = workspace / "src" / "module.py"
    target.parent.mkdir(parents=True)
    target.write_text(
        "do_thing()\n"
        "noisy_print()  # atdd:suppress(SMOKE-SC-001) UNTIL=2099-01-01\n"
    )

    # The fixture validator. Uses bare imports of atdd.coach.* — these
    # resolve via PYTHONPATH which the test injects into the subprocess.
    validator = workspace / "tests" / "test_smoke_validator.py"
    validator.parent.mkdir(parents=True)
    validator.write_text(textwrap.dedent("""
        from pathlib import Path
        import pytest
        from atdd.coach.utils.disposition_gate import assert_disposition_satisfied
        from atdd.coach.utils.rule_id_registry import RuleMetadata
        from atdd.coach.validators._violation import Violation


        REGISTRY = {
            "SMOKE-STRICT-001": RuleMetadata(
                rule_id="SMOKE-STRICT-001",
                convention_path=Path("/dev/null"),
                severity=4,
                description="strict fixture rule",
                disposition="strict",
            ),
            "SMOKE-ADV-001": RuleMetadata(
                rule_id="SMOKE-ADV-001",
                convention_path=Path("/dev/null"),
                severity=1,
                description="advisory fixture rule",
                disposition="advisory",
            ),
            "SMOKE-SC-001": RuleMetadata(
                rule_id="SMOKE-SC-001",
                convention_path=Path("/dev/null"),
                severity=2,
                description="suppress-and-clean fixture rule",
                disposition="suppress-and-clean",
            ),
        }


        def test_advisory_fires(tmp_path):
            v = Violation(
                rule_id="SMOKE-ADV-001",
                severity=1,
                location="src/module.py:1",
                detail="advisory",
            )
            # Advisory passes silently but is captured.
            assert_disposition_satisfied(
                validator_id="tests/test_smoke_validator.py::test_advisory_fires",
                violations=[v],
                registry=REGISTRY,
                repo_root=Path(__file__).resolve().parents[1],
            )


        def test_suppress_and_clean_absorbed(tmp_path):
            v = Violation(
                rule_id="SMOKE-SC-001",
                severity=2,
                location="src/module.py:2",
                detail="absorbed by inline marker",
            )
            assert_disposition_satisfied(
                validator_id="tests/test_smoke_validator.py::test_suppress_and_clean_absorbed",
                violations=[v],
                registry=REGISTRY,
                repo_root=Path(__file__).resolve().parents[1],
            )


        def test_strict_fails():
            # Intentionally lets pytest.fail propagate so the subprocess
            # exit code is non-zero — proves the plugin still flushes
            # captured records when validators fail.
            v = Violation(
                rule_id="SMOKE-STRICT-001",
                severity=4,
                location="src/module.py:1",
                detail="strict",
            )
            assert_disposition_satisfied(
                validator_id="tests/test_smoke_validator.py::test_strict_fails",
                violations=[v],
                registry=REGISTRY,
                repo_root=Path(__file__).resolve().parents[1],
            )
    """).lstrip())

    # Inject this worktree's src/ so the fixture's imports resolve before
    # autoload disables anything ambient.
    pythonpath_existing = os.environ.get("PYTHONPATH", "")
    pythonpath_full = (
        f"{_worktree_src()}{os.pathsep}{pythonpath_existing}"
        if pythonpath_existing
        else str(_worktree_src())
    )

    sha = "smoke" + "0" * 35  # 40-char-ish, not a real SHA
    runtime_dir = tmp_path / "runtime"

    # Patch the subprocess env via monkeypatch so isolation is preserved
    # under parallel pytest runs. PYTHONPATH and ATDD_DIAGNOSTICS_DISABLED
    # are picked up by the dispatcher's whitelisted passthrough.
    monkeypatch.setenv("PYTHONPATH", pythonpath_full)
    monkeypatch.setenv("ATDD_DIAGNOSTICS_DISABLED", "1")
    result = dispatch_validators(
        sha=sha,
        validator_paths=[validator],
        repo_root=workspace,
        runtime_dir=runtime_dir,
    )

    # The strict test fails — pytest exit is 1, but the plugin must still
    # have flushed all observed violations.
    assert result.exit_code == 1, (
        f"expected pytest exit=1 (strict fixture fails), "
        f"got {result.exit_code}\nstdout={result.stdout}\nstderr={result.stderr}"
    )

    out = result.violations_path
    assert out.exists(), (
        f"violations.jsonl not flushed at {out}\n"
        f"stdout={result.stdout}\nstderr={result.stderr}"
    )

    records = _read_jsonl(out)
    rule_ids = sorted(r["rule_id"] for r in records)
    # All three disposition flavors recorded — no losses.
    assert rule_ids == ["SMOKE-ADV-001", "SMOKE-SC-001", "SMOKE-STRICT-001"], rule_ids

    # Schema conformance for every record.
    schema = _validator_schema()
    for record in records:
        errors = list(schema.iter_errors(record))
        assert errors == [], (
            f"smoke record {record.get('rule_id')!r} failed schema: "
            f"{[e.message for e in errors]}"
        )

    # Suppression marker text round-trips through the subprocess for the
    # suppress-and-clean record.
    sc = next(r for r in records if r["rule_id"] == "SMOKE-SC-001")
    assert sc["suppression_marker"] is not None
    assert "atdd:suppress(SMOKE-SC-001)" in sc["suppression_marker"]
