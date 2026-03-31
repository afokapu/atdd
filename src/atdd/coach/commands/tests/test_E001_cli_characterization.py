"""
CLI characterization tests for ATDD toolkit self-compliance migration.

SPEC: wmbt:self-compliance-migration:E001
ID: SPEC-SELF-COMPLIANCE-E001

Acceptance URNs covered by this test file:
  acc:self-compliance-migration:C001-UNIT-001-baseline-passes
  acc:self-compliance-migration:D001-UNIT-001-wagon-manifests-exist
  acc:self-compliance-migration:D002-UNIT-001-feature-refs-wmbts
  acc:self-compliance-migration:E001-UNIT-001-characterization-tests-pass
  acc:self-compliance-migration:E002-UNIT-001-contracts-pass-schema
  acc:self-compliance-migration:P001-UNIT-001-train-validates
  acc:self-compliance-migration:R001-UNIT-001-urn-validate-passes
  acc:self-compliance-migration:K001-UNIT-001-dual-gate-passes

Purpose:
  Lock current CLI entrypoint behavior as a regression safety net.
  These tests verify machine-readable outputs and structural invariants
  of CLI commands that do NOT require GitHub API access.

Architecture:
  - Tests invoke CLI functions directly (no subprocess)
  - JSON outputs are validated for structural keys, not exact values
  - Human-readable outputs are validated for structural patterns
  - No mocking — tests run against the real repo state

Gate:
  - Local pytest only (not atdd validate)
  - These tests live under coach/commands/tests/ and are exercised
    by `python3 -m pytest src/atdd -q`, not by `atdd validate`
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[5]


# ============================================================================
# Helpers
# ============================================================================

def run_atdd(*args: str, expect_rc: int = 0) -> subprocess.CompletedProcess:
    """Run atdd CLI as subprocess and return result."""
    cmd = [sys.executable, "-m", "atdd"] + list(args)
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        env={
            **__import__("os").environ,
            "PYTHONPATH": str(REPO_ROOT / "src"),
        },
    )
    assert result.returncode == expect_rc, (
        f"atdd {' '.join(args)} exited {result.returncode}, "
        f"expected {expect_rc}.\nstderr: {result.stderr}\nstdout: {result.stdout}"
    )
    return result


# ============================================================================
# E001-001: atdd version
# ============================================================================

class TestVersionCommand:
    """Characterize `atdd version` output format."""

    def test_version_prints_semver(self):
        """
        SPEC-SELF-COMPLIANCE-E001-001: version command prints semver string.

        Given: atdd CLI is installed
        When: Running `atdd version`
        Then: Output matches pattern `atdd X.Y.Z`
        """
        result = run_atdd("version")
        import re
        assert re.match(r"^atdd \d+\.\d+\.\d+\n?$", result.stdout), (
            f"Version output does not match 'atdd X.Y.Z': {result.stdout!r}"
        )

    def test_version_flag(self):
        """
        SPEC-SELF-COMPLIANCE-E001-002: --version flag prints version.

        Given: atdd CLI is installed
        When: Running `atdd --version`
        Then: Output matches pattern `atdd X.Y.Z`
        """
        result = run_atdd("--version")
        assert result.stdout.startswith("atdd "), (
            f"--version output should start with 'atdd ': {result.stdout!r}"
        )


# ============================================================================
# E001-002: atdd gate --json
# ============================================================================

class TestGateCommand:
    """Characterize `atdd gate --json` output structure."""

    def test_gate_json_has_required_keys(self):
        """
        SPEC-SELF-COMPLIANCE-E001-010: gate --json returns required top-level keys.

        Given: ATDD is initialized in the repo
        When: Running `atdd gate --json`
        Then: JSON output contains files, constraints keys
        """
        result = run_atdd("gate", "--json")
        data = json.loads(result.stdout)
        assert "files" in data, "gate --json must have 'files' key"
        assert "constraints" in data, "gate --json must have 'constraints' key"

    def test_gate_json_constraints_is_list(self):
        """
        SPEC-SELF-COMPLIANCE-E001-011: gate constraints is a non-empty list of strings.

        Given: ATDD gate --json output
        When: Inspecting constraints
        Then: constraints is a list with at least 1 string entry
        """
        result = run_atdd("gate", "--json")
        data = json.loads(result.stdout)
        constraints = data["constraints"]
        assert isinstance(constraints, list), "constraints must be a list"
        assert len(constraints) >= 1, "constraints must have at least 1 entry"
        assert all(isinstance(c, str) for c in constraints), (
            "all constraints must be strings"
        )

    def test_gate_json_files_has_claude(self):
        """
        SPEC-SELF-COMPLIANCE-E001-012: gate files includes claude config.

        Given: ATDD gate --json output
        When: Inspecting files
        Then: files contains a 'claude' entry with exists, has_block, hash keys
        """
        result = run_atdd("gate", "--json")
        data = json.loads(result.stdout)
        files = data["files"]
        assert "claude" in files, "files must have 'claude' key"
        claude = files["claude"]
        assert "exists" in claude, "claude entry must have 'exists'"
        assert "has_block" in claude, "claude entry must have 'has_block'"
        assert "hash" in claude, "claude entry must have 'hash'"


# ============================================================================
# E001-003: atdd inventory --format json
# ============================================================================

class TestInventoryCommand:
    """Characterize `atdd inventory --format json` output structure."""

    def test_inventory_json_has_inventory_key(self):
        """
        SPEC-SELF-COMPLIANCE-E001-020: inventory JSON wraps data under 'inventory' key.

        Given: ATDD inventory command
        When: Running `atdd inventory --format json`
        Then: JSON output has top-level 'inventory' key
        """
        result = run_atdd("inventory", "--format", "json")
        # Inventory prints progress to stdout before JSON; extract JSON portion
        stdout = result.stdout
        json_start = stdout.index("{")
        data = json.loads(stdout[json_start:])
        assert "inventory" in data, "inventory JSON must have 'inventory' key"

    def test_inventory_json_has_structural_sections(self):
        """
        SPEC-SELF-COMPLIANCE-E001-021: inventory JSON has expected section keys.

        Given: ATDD inventory --format json
        When: Inspecting the inventory object
        Then: Contains trains, wagons, tests, implementations sections
        """
        result = run_atdd("inventory", "--format", "json")
        stdout = result.stdout
        json_start = stdout.index("{")
        data = json.loads(stdout[json_start:])
        inv = data["inventory"]
        expected_keys = {"trains", "wagons", "tests", "implementations"}
        actual_keys = set(inv.keys())
        missing = expected_keys - actual_keys
        assert not missing, f"inventory missing sections: {missing}"

    def test_inventory_json_trains_have_total(self):
        """
        SPEC-SELF-COMPLIANCE-E001-022: trains section has 'total' count.

        Given: ATDD inventory --format json
        When: Inspecting trains section
        Then: trains has 'total' integer field
        """
        result = run_atdd("inventory", "--format", "json")
        stdout = result.stdout
        json_start = stdout.index("{")
        data = json.loads(stdout[json_start:])
        trains = data["inventory"]["trains"]
        assert "total" in trains, "trains must have 'total' key"
        assert isinstance(trains["total"], int), "trains.total must be an integer"


# ============================================================================
# E001-004: atdd status
# ============================================================================

class TestStatusCommand:
    """Characterize `atdd status` output structure."""

    def test_status_shows_validator_counts(self):
        """
        SPEC-SELF-COMPLIANCE-E001-030: status shows validator file counts.

        Given: ATDD status command
        When: Running `atdd status`
        Then: Output contains Planner/Tester/Coder/Coach counts and Total line
        """
        result = run_atdd("status")
        stdout = result.stdout
        for phase in ("Planner", "Tester", "Coder", "Coach", "Total"):
            assert phase in stdout, f"status output must mention '{phase}'"

    def test_status_shows_total_72_validators(self):
        """
        SPEC-SELF-COMPLIANCE-E001-031: status total matches current validator count.

        Given: ATDD status command
        When: Running `atdd status`
        Then: Total line shows 73 files (current validator count)
        """
        result = run_atdd("status")
        assert "73 files" in result.stdout, (
            f"status total should show '73 files', got: {result.stdout}"
        )


# ============================================================================
# E001-005: atdd urn families
# ============================================================================

class TestUrnFamiliesCommand:
    """Characterize `atdd urn families` output."""

    def test_urn_families_lists_core_families(self):
        """
        SPEC-SELF-COMPLIANCE-E001-040: urn families includes core URN families.

        Given: ATDD urn families command
        When: Running `atdd urn families`
        Then: Output lists at minimum: wagon, train, wmbt, contract, telemetry, feature
        """
        result = run_atdd("urn", "families")
        stdout = result.stdout
        core_families = ["wagon", "train", "wmbt", "contract", "telemetry", "feature"]
        for family in core_families:
            assert family in stdout, (
                f"urn families must include '{family}'"
            )


# ============================================================================
# E001-006: atdd --help
# ============================================================================

class TestHelpCommand:
    """Characterize `atdd --help` output structure."""

    def test_help_lists_all_subcommands(self):
        """
        SPEC-SELF-COMPLIANCE-E001-050: --help lists all registered subcommands.

        Given: ATDD CLI
        When: Running `atdd --help`
        Then: Output mentions all core subcommands
        """
        result = run_atdd("--help")
        stdout = result.stdout
        core_commands = [
            "validate", "inventory", "status", "registry", "init",
            "issue", "list", "branch", "color", "sync", "gate", "urn",
        ]
        for cmd in core_commands:
            assert cmd in stdout, f"--help must mention subcommand '{cmd}'"
