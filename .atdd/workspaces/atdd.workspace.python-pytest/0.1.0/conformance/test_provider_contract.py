"""Conformance suite for atdd.workspace.python-pytest (contract_version 1.1.0).

A real pytest run — not a stub — proving the provider's discover + run halves
satisfy the contract. A different runtime (node-vitest, go-test) claiming this
contract proves it by making an equivalent suite pass.

Split into v1.0.0 (exit-code fallback, unchanged) and v1.1.0 (structured report
channel + scan-mount) sections so back-compat is visible at a glance.
"""
from __future__ import annotations

import json
import sys
import textwrap
from pathlib import Path

import pytest

# Import the provider adapter (sibling ../adapter) without packaging it.
_ADAPTER = Path(__file__).resolve().parent.parent / "adapter"
sys.path.insert(0, str(_ADAPTER))

import discover as discover_mod  # noqa: E402
import run as run_mod  # noqa: E402


def _impl_manifest(impl_id: str, contract_version: str) -> str:
    return textwrap.dedent(
        f"""\
        kind: implementation
        implementation_id: {impl_id}
        targets_workspace: atdd.workspace.python-pytest
        contract_version: "{contract_version}"
        """
    )


# ── discover ────────────────────────────────────────────────────────────────


def test_discover_returns_only_contract_compatible(tmp_path: Path) -> None:
    (tmp_path / "ok").mkdir()
    (tmp_path / "ok" / "atdd.implementation.yaml").write_text(_impl_manifest("ext.ok", "1.0.0"))
    (tmp_path / "newer").mkdir()
    # 2.0.0 requires a newer provider major → incompatible, must be skipped.
    (tmp_path / "newer" / "atdd.implementation.yaml").write_text(_impl_manifest("ext.newer", "2.0.0"))

    found = discover_mod.discover_implementations(tmp_path)

    assert [i.implementation_id for i in found] == ["ext.ok"]
    assert found[0].targets_workspace == "atdd.workspace.python-pytest"


def test_discover_skips_malformed_and_non_implementation(tmp_path: Path) -> None:
    (tmp_path / "bad").mkdir()
    (tmp_path / "bad" / "atdd.implementation.yaml").write_text(": not: valid: yaml:")
    (tmp_path / "wrongkind").mkdir()
    (tmp_path / "wrongkind" / "atdd.implementation.yaml").write_text("kind: workspace\n")

    assert discover_mod.discover_implementations(tmp_path) == []


@pytest.mark.parametrize(
    "impl,provider,expected",
    [
        ("1.0.0", "1.0.0", True),
        ("1.0.0", "1.2.0", True),   # older impl on newer provider: ok
        ("1.3.0", "1.2.0", False),  # impl needs newer minor than provider: no
        ("2.0.0", "1.0.0", False),  # major mismatch: no
    ],
)
def test_contract_compatible(impl: str, provider: str, expected: bool) -> None:
    assert discover_mod.contract_compatible(impl, provider) is expected


# ── run ──────────────────────────────────────────────────────────────────────


def test_run_passing_yields_no_violations(tmp_path: Path) -> None:
    test_file = tmp_path / "test_pass.py"
    test_file.write_text("def test_ok():\n    assert 1 == 1\n")

    result = run_mod.run_implementation("ext.ok", test_file)

    assert result.ran
    assert result.passed
    assert result.exit_code == 0
    assert result.violations == []


def test_run_failing_yields_one_violation_keyed_by_impl(tmp_path: Path) -> None:
    test_file = tmp_path / "test_fail.py"
    test_file.write_text("def test_bad():\n    assert 1 == 2\n")

    result = run_mod.run_implementation("ext.bad", test_file)

    assert result.ran
    assert not result.passed
    assert result.exit_code == 1
    assert not result.structured  # v1.0.0 fallback channel
    assert len(result.violations) == 1
    assert result.violations[0]["rule_id"] == "ext.bad"
    assert result.violations[0]["location"] == "."


# ── v1.1: structured report channel + scan-mount ─────────────────────────────


def _report_writer_test(violations_literal: str) -> str:
    """A test file that writes a v1.1 report to $ATDD_VIOLATIONS_REPORT and passes."""
    return textwrap.dedent(
        f"""\
        import json, os
        def test_emit():
            path = os.environ.get("ATDD_VIOLATIONS_REPORT")
            if path:
                with open(path, "w") as fh:
                    json.dump({{"contract_version": "1.1.0",
                               "violations": {violations_literal}}}, fh)
            assert True
        """
    )


def test_run_reads_structured_report_channel(tmp_path: Path) -> None:
    """A run that emits a report returns its RAW violations (structured=True)."""
    viol = (
        '[{"rule_id": "coder.logging.structured", "file": "a.py", "line": 3, '
        '"col": 4, "evidence": "no extra=", "source_line": "logger.info(\\"x\\")"}]'
    )
    test_file = tmp_path / "test_emit.py"
    test_file.write_text(_report_writer_test(viol))

    result = run_mod.run_implementation("coder.logging.structured", test_file)

    assert result.ran
    assert result.structured
    assert len(result.violations) == 1
    v = result.violations[0]
    assert v["rule_id"] == "coder.logging.structured"
    assert v["line"] == 3 and v["col"] == 4
    assert "source_line" in v  # RAW line carried for downstream disposition


def test_run_emits_multiple_distinct_rule_ids(tmp_path: Path) -> None:
    """One run may carry several distinct rule_ids (gap 3 — multi-rule)."""
    viol = (
        '[{"rule_id": "coder.logging.print", "file": "a.py", "line": 1, "col": 0,'
        ' "evidence": "print", "source_line": "print(1)"},'
        ' {"rule_id": "coder.logging.structured", "file": "a.py", "line": 2, "col": 0,'
        ' "evidence": "no extra", "source_line": "logger.info(2)"}]'
    )
    test_file = tmp_path / "test_multi.py"
    test_file.write_text(_report_writer_test(viol))

    result = run_mod.run_implementation("multi", test_file)

    assert result.structured
    assert {v["rule_id"] for v in result.violations} == {
        "coder.logging.print",
        "coder.logging.structured",
    }


def test_run_malformed_report_falls_back_not_silent_pass(tmp_path: Path) -> None:
    """A malformed report must NOT be read as zero violations — fall back instead."""
    bad = textwrap.dedent(
        """\
        import os
        def test_emit():
            path = os.environ.get("ATDD_VIOLATIONS_REPORT")
            if path:
                with open(path, "w") as fh:
                    fh.write("not json {{{")
            assert 1 == 2
        """
    )
    test_file = tmp_path / "test_bad_report.py"
    test_file.write_text(bad)

    result = run_mod.run_implementation("ext.bad", test_file)

    # Malformed report -> v1.0.0 fallback (exit-code mapping), not a clean pass.
    assert not result.structured
    assert not result.passed
    assert result.violations == [
        v for v in result.violations if v.get("location") == "."
    ]
    assert result.violations and result.violations[0]["rule_id"] == "ext.bad"


def test_run_injects_scan_roots_and_excludes(tmp_path: Path) -> None:
    """scan_roots / exclude_globs are injected as JSON env vars for the detector."""
    test_file = tmp_path / "test_env.py"
    test_file.write_text(
        textwrap.dedent(
            """\
            import json, os
            def test_emit():
                roots = json.loads(os.environ["ATDD_SCAN_ROOTS"])
                excl = json.loads(os.environ["ATDD_SCAN_EXCLUDES"])
                assert roots == ["python", "web/src"]
                assert excl == ["**/migrations/**"]
            """
        )
    )

    result = run_mod.run_implementation(
        "ext.scan",
        test_file,
        scan_roots=["python", "web/src"],
        exclude_globs=["**/migrations/**"],
    )

    assert result.ran
    assert result.passed  # the in-subprocess assertions held
