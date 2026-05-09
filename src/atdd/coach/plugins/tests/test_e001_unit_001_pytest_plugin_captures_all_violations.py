# URN: test:dispatch-validators:dispatch-tier-one-validators:E001-UNIT-001-pytest-plugin-captures-all-violations
# Acceptance: acc:dispatch-validators:E001-UNIT-001-pytest-plugin-captures-all-violations
# WMBT: wmbt:dispatch-validators:E001
# Phase: RED
# Layer: integration
# Assertion: behavioral
"""E001-UNIT-001 — pytest plugin captures every Violation emitted via
``assert_disposition_satisfied`` and writes them to
``.atdd/runtime/validations/<sha>/violations.jsonl``.

Per spec §6.4 step 4 / §7.5 / validator-invocation.md: when coach invokes
pytest with ``-p atdd.coach.plugins.violation_collector``, the plugin
intercepts every Violation that flows through the substrate's disposition
gate and appends one JSON record per violation to the SHA-keyed JSONL.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, List, Optional

import pytest


def _make_session(repo_root: Path) -> Any:
    """Duck-typed pytest.Session sufficient for the collector's hooks."""
    config = SimpleNamespace(args=[], rootpath=repo_root, workerinput=None)
    return SimpleNamespace(config=config, items=[], _atdd={})


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


# ---------------------------------------------------------------------------
# Plugin existence + module location (validator-invocation.md contract).
# ---------------------------------------------------------------------------


def test_plugin_module_importable_at_canonical_path():
    """Per validator-invocation.md, the plugin module must be importable
    as ``atdd.coach.plugins.violation_collector`` so coach can attach it via
    ``-p atdd.coach.plugins.violation_collector``."""
    import importlib

    mod = importlib.import_module("atdd.coach.plugins.violation_collector")
    assert hasattr(mod, "pytest_sessionstart")
    assert hasattr(mod, "pytest_sessionfinish")


# ---------------------------------------------------------------------------
# Strict, suppress-and-clean (suppressed + unsuppressed), advisory all flow.
# ---------------------------------------------------------------------------


def test_plugin_captures_strict_violation(tmp_path, monkeypatch):
    """A strict-disposition violation surfaces in violations.jsonl."""
    from atdd.coach.plugins import violation_collector as plugin
    from atdd.coach.utils import disposition_gate
    from atdd.coach.utils.rule_id_registry import RuleMetadata
    from atdd.coach.validators._violation import Violation

    sha = "0" * 40
    monkeypatch.setenv("ATDD_VALIDATION_SHA", sha)
    monkeypatch.setenv("ATDD_RUNTIME_DIR", str(tmp_path / "runtime"))

    target = tmp_path / "src/code.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("print('x')\n")

    session = _make_session(tmp_path)
    plugin.pytest_sessionstart(session)

    registry = {
        "LOG-PRINT-001": RuleMetadata(
            rule_id="LOG-PRINT-001",
            convention_path=Path("/dev/null"),
            severity=3,
            description="no print",
            disposition="strict",
        ),
    }
    v = Violation(
        rule_id="LOG-PRINT-001",
        severity=3,
        location=f"{target.relative_to(tmp_path)}:1",
        detail="print() in production code",
    )
    with pytest.raises(pytest.fail.Exception):
        disposition_gate.assert_disposition_satisfied(
            validator_id="src/code.py::test_no_print",
            violations=[v],
            registry=registry,
            repo_root=tmp_path,
        )

    plugin.pytest_sessionfinish(session, exitstatus=1)
    disposition_gate.set_active_pytest_session(None)

    out = tmp_path / "runtime" / "validations" / sha / "violations.jsonl"
    assert out.exists(), "violations.jsonl was not written"
    records = _read_jsonl(out)
    assert len(records) == 1
    record = records[0]
    assert record["rule_id"] == "LOG-PRINT-001"
    assert record["severity"] == 3
    assert record["disposition"] == "strict"
    assert record["detail"] == "print() in production code"
    assert record["suppression_marker"] is None
    assert record["validator_id"] == "src/code.py::test_no_print"


def test_plugin_captures_advisory_violation(tmp_path, monkeypatch):
    """Advisory disposition still produces a record (visible to coach)."""
    from atdd.coach.plugins import violation_collector as plugin
    from atdd.coach.utils import disposition_gate
    from atdd.coach.utils.rule_id_registry import RuleMetadata
    from atdd.coach.validators._violation import Violation

    sha = "1" * 40
    monkeypatch.setenv("ATDD_VALIDATION_SHA", sha)
    monkeypatch.setenv("ATDD_RUNTIME_DIR", str(tmp_path / "runtime"))

    target = tmp_path / "src/code.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("noop\n")

    session = _make_session(tmp_path)
    plugin.pytest_sessionstart(session)

    registry = {
        "ADV-NOTE-001": RuleMetadata(
            rule_id="ADV-NOTE-001",
            convention_path=Path("/dev/null"),
            severity=1,
            description="note",
            disposition="advisory",
        ),
    }
    v = Violation(
        rule_id="ADV-NOTE-001",
        severity=1,
        location=f"{target.relative_to(tmp_path)}:1",
        detail="advisory note",
    )
    # Advisory passes silently, but must still be captured.
    disposition_gate.assert_disposition_satisfied(
        validator_id="src/code.py::test_advisory",
        violations=[v],
        registry=registry,
        repo_root=tmp_path,
    )

    plugin.pytest_sessionfinish(session, exitstatus=0)
    disposition_gate.set_active_pytest_session(None)

    out = tmp_path / "runtime" / "validations" / sha / "violations.jsonl"
    records = _read_jsonl(out)
    assert len(records) == 1
    assert records[0]["rule_id"] == "ADV-NOTE-001"
    assert records[0]["disposition"] == "advisory"
    assert records[0]["suppression_marker"] is None


def test_plugin_captures_suppress_and_clean_with_marker(tmp_path, monkeypatch):
    """A suppress-and-clean violation absorbed by an inline marker is captured
    with a non-null ``suppression_marker`` field."""
    from atdd.coach.plugins import violation_collector as plugin
    from atdd.coach.utils import disposition_gate
    from atdd.coach.utils.rule_id_registry import RuleMetadata
    from atdd.coach.validators._violation import Violation

    sha = "2" * 40
    monkeypatch.setenv("ATDD_VALIDATION_SHA", sha)
    monkeypatch.setenv("ATDD_RUNTIME_DIR", str(tmp_path / "runtime"))

    target = tmp_path / "src/code.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "print('x')  # atdd:suppress(LOG-PRINT-002) UNTIL=2099-01-01\n"
    )

    session = _make_session(tmp_path)
    plugin.pytest_sessionstart(session)

    registry = {
        "LOG-PRINT-002": RuleMetadata(
            rule_id="LOG-PRINT-002",
            convention_path=Path("/dev/null"),
            severity=2,
            description="no print",
            disposition="suppress-and-clean",
        ),
    }
    v = Violation(
        rule_id="LOG-PRINT-002",
        severity=2,
        location=f"{target.relative_to(tmp_path)}:1",
        detail="print() in production code",
    )
    # Inline marker absorbs the violation — gate passes silently.
    disposition_gate.assert_disposition_satisfied(
        validator_id="src/code.py::test_print_clean",
        violations=[v],
        registry=registry,
        repo_root=tmp_path,
    )

    plugin.pytest_sessionfinish(session, exitstatus=0)
    disposition_gate.set_active_pytest_session(None)

    out = tmp_path / "runtime" / "validations" / sha / "violations.jsonl"
    records = _read_jsonl(out)
    assert len(records) == 1
    record = records[0]
    assert record["rule_id"] == "LOG-PRINT-002"
    assert record["disposition"] == "suppress-and-clean"
    assert record["suppression_marker"] is not None
    assert "atdd:suppress(LOG-PRINT-002)" in record["suppression_marker"]


def test_plugin_captures_mixed_dispositions_no_loss_no_dupes(tmp_path, monkeypatch):
    """All Violations across a single test run are captured exactly once."""
    from atdd.coach.plugins import violation_collector as plugin
    from atdd.coach.utils import disposition_gate
    from atdd.coach.utils.rule_id_registry import RuleMetadata
    from atdd.coach.validators._violation import Violation

    sha = "3" * 40
    monkeypatch.setenv("ATDD_VALIDATION_SHA", sha)
    monkeypatch.setenv("ATDD_RUNTIME_DIR", str(tmp_path / "runtime"))

    code = tmp_path / "src/code.py"
    code.parent.mkdir(parents=True, exist_ok=True)
    code.write_text("a\nb\nc\nd\n")

    session = _make_session(tmp_path)
    plugin.pytest_sessionstart(session)

    registry = {
        "STRICT-001": RuleMetadata(
            rule_id="STRICT-001",
            convention_path=Path("/dev/null"),
            severity=4,
            description="x",
            disposition="strict",
        ),
        "ADV-001": RuleMetadata(
            rule_id="ADV-001",
            convention_path=Path("/dev/null"),
            severity=1,
            description="x",
            disposition="advisory",
        ),
    }
    rel = code.relative_to(tmp_path)
    strict_a = Violation(rule_id="STRICT-001", severity=4, location=f"{rel}:1", detail="A")
    strict_b = Violation(rule_id="STRICT-001", severity=4, location=f"{rel}:2", detail="B")
    adv_c = Violation(rule_id="ADV-001", severity=1, location=f"{rel}:3", detail="C")

    # Advisory call passes; strict call fails — both must record.
    disposition_gate.assert_disposition_satisfied(
        validator_id="vid::adv",
        violations=[adv_c],
        registry=registry,
        repo_root=tmp_path,
    )
    with pytest.raises(pytest.fail.Exception):
        disposition_gate.assert_disposition_satisfied(
            validator_id="vid::strict",
            violations=[strict_a, strict_b],
            registry=registry,
            repo_root=tmp_path,
        )

    plugin.pytest_sessionfinish(session, exitstatus=1)
    disposition_gate.set_active_pytest_session(None)

    out = tmp_path / "runtime" / "validations" / sha / "violations.jsonl"
    records = _read_jsonl(out)
    # Three violations in, three records out — one per Violation.
    assert len(records) == 3, f"expected 3 records, got {len(records)}: {records}"
    keyed = sorted((r["rule_id"], r["detail"]) for r in records)
    assert keyed == [
        ("ADV-001", "C"),
        ("STRICT-001", "A"),
        ("STRICT-001", "B"),
    ]


# ---------------------------------------------------------------------------
# Plugin loading discipline.
# ---------------------------------------------------------------------------


def test_plugin_runs_with_disabled_autoload_subprocess(tmp_path):
    """Per validator-invocation.md §2: coach sets PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
    and registers solely via ``-p atdd.coach.plugins.violation_collector``. We
    simulate that invocation in a subprocess and verify the plugin still loads
    and writes ``violations.jsonl`` for the run's sha.
    """
    sha = "4" * 40
    runtime_dir = tmp_path / "runtime"
    workdir = tmp_path / "wt"
    workdir.mkdir(parents=True, exist_ok=True)

    # A trivial passing test so pytest exits cleanly.
    (workdir / "test_noop.py").write_text(
        "def test_noop():\n    assert True\n"
    )

    env = dict(os.environ)
    env.update(
        {
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
            "ATDD_VALIDATION_SHA": sha,
            "ATDD_RUNTIME_DIR": str(runtime_dir),
            "ATDD_DIAGNOSTICS_DISABLED": "1",  # keep stdout quiet
        }
    )
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "--rootdir",
            str(workdir),
            "-p",
            "atdd.coach.plugins.violation_collector",
            str(workdir),
        ],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(workdir),
    )
    assert proc.returncode == 0, f"pytest failed: {proc.stdout}\n{proc.stderr}"

    # JSONL file exists even when zero violations are captured (the plugin
    # creates the parent dir and writes an empty file so coach can detect
    # "ran but clean" vs "did not run").
    out = runtime_dir / "validations" / sha / "violations.jsonl"
    assert out.exists(), (
        f"plugin did not initialize violations.jsonl at {out}; "
        f"stdout={proc.stdout}\nstderr={proc.stderr}"
    )
    assert out.read_text() == "", "no violations expected from passing run"
