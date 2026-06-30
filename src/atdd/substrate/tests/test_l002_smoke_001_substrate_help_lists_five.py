# URN: test:admit-substrate:substrate-cli-grouping:L002-SMOKE-001-substrate-help-lists-five
# Acceptance: acc:admit-substrate:L002-SMOKE-001-substrate-help-lists-five
# WMBT: wmbt:admit-substrate:L002
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""L002-SMOKE-001 (V3) — `atdd substrate --help` lists the five subcommands; the
deprecated flat `atdd add --help` is marked [DEPRECATED] and points to the
grouped form."""
from __future__ import annotations


def test_substrate_help_lists_five_subcommands(tmp_path, run_atdd) -> None:
    proc = run_atdd(["substrate", "--help"], tmp_path)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    out = proc.stdout
    for sub in ("add", "remove", "bind", "capabilities", "list"):
        assert sub in out, f"{sub!r} missing from `atdd substrate --help`:\n{out}"


def test_flat_add_help_marks_deprecated(tmp_path, run_atdd) -> None:
    proc = run_atdd(["add", "--help"], tmp_path)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "DEPRECATED" in proc.stdout
    assert "substrate add" in proc.stdout
