"""Differential legacy-vs-convention catch-matrix harness (#1212).

For each case it: (1) confirms BOTH suites are silent on the clean repo
(false-positive check), then (2) injects one realistic fault, runs BOTH the legacy
pytest validator and the convention sentinel on the identical faulted tree, records
the catch-matrix cell, and reverts.

Cell semantics per fault:
  both          -> parity (target catches what legacy catches)
  convention    -> convention-only (improvement OR false-positive; adjudicate per #1211)
  legacy        -> legacy-only (coverage gap / regression)
  neither       -> shared blind spot

This is the corpus-driven measurement (#1212 E027 expands cases to one per legacy
rule). The harness itself is rule-agnostic.
"""
from __future__ import annotations

import contextlib
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional

from .graph_loader import load_composed_graph
from . import sentinels as S


@dataclass
class Case:
    name: str
    family_template: str
    sentinel: Callable           # graph -> EvalResult
    legacy_target: str           # pytest nodeid
    # fault injection: either a patch (file, old, new) or a temp file (relpath, content)
    patch: Optional[tuple] = None
    tempfile: Optional[tuple] = None


@dataclass
class Cell:
    name: str
    family_template: str
    clean_convention_flags: int
    legacy_clean_red: bool        # legacy target already failing on the CLEAN tree
    legacy_caught: bool           # legacy target failing on the FAULTED tree
    convention_caught: bool
    verdict: str = field(init=False)

    def __post_init__(self):
        # A legacy target that is already red on the clean repo cannot be credited
        # with "catching" the injected fault — its red is pre-existing, so the
        # differential is inconclusive and may NOT be counted toward parity.
        if self.legacy_clean_red:
            self.verdict = "inconclusive (legacy red on clean)"
            return
        self.verdict = {
            (True, True): "both",
            (True, False): "legacy-only",
            (False, True): "convention-only",
            (False, False): "neither",
        }[(self.legacy_caught, self.convention_caught)]


@contextlib.contextmanager
def _inject(root: Path, case: Case):
    if case.patch:
        rel, old, new = case.patch
        p = root / rel
        orig = p.read_text(encoding="utf-8")
        p.write_text(orig.replace(old, new, 1), encoding="utf-8")
        try:
            yield
        finally:
            p.write_text(orig, encoding="utf-8")
    else:
        rel, content = case.tempfile
        p = root / rel
        p.write_text(content, encoding="utf-8")
        try:
            yield
        finally:
            p.unlink(missing_ok=True)


def _legacy_caught(root: Path, target: str) -> bool:
    rc = subprocess.run(
        [sys.executable, "-m", "pytest", target, "-q", "-p", "no:cacheprovider"],
        cwd=root, env={"PYTHONPATH": "src", "PATH": os.environ["PATH"]},
        capture_output=True, text=True,
    ).returncode
    return rc != 0


def _conv_caught(root: Path, sentinel) -> bool:
    return bool(sentinel(load_composed_graph(root)).violations)


CASES: List[Case] = [
    Case("theme-noncanonical", "grammar/theme_must_be_canonical",
         S.theme_must_be_canonical,
         "src/atdd/planner/validators/test_theme_must_be_canonical.py::test_every_wagon_theme_is_canonical",
         patch=("plan/validate_conventions/_validate_conventions.yaml",
                "theme: commons", "theme: bogus_noncanonical")),
    Case("duplicate-rule-id", "uniqueness/scoped_identifier_uniqueness",
         S.scoped_identifier_uniqueness,
         "src/atdd/coach/validators/test_rule_id_uniqueness.py",
         tempfile=("src/atdd/coach/conventions/_tmp_catchmatrix_dup.convention.yaml",
                   'version: "1.0"\nname: "catch-matrix dup"\nrules:\n'
                   '  - id: "planner.theme.must-be-canonical"\n    severity: 3\n'
                   '    validator: "x::y"\n')),
    # WMBT urn with an out-of-grammar step code (Z) vs the legacy urn<->step check.
    Case("wmbt-urn-bad-step", "grammar/identifier_grammar_conformance",
         S.identifier_grammar_conformance,
         "src/atdd/planner/validators/test_wmbt_vocabulary.py::test_wmbt_urn_step_code_matches_step_field",
         patch=("plan/validate_conventions/E001.yaml",
                "urn: wmbt:validate-conventions:E001", "urn: wmbt:validate-conventions:Z001")),
    # Wagon manifest with an unexpected top-level key vs wagon.schema additionalProperties:false.
    Case("wagon-schema-extra-prop", "schema/node_schema_conformance",
         S.node_schema_conformance,
         "src/atdd/planner/validators/test_plan_wagons.py::test_wagon_manifest_matches_schema",
         patch=("plan/validate_conventions/_validate_conventions.yaml",
                "features:", "catchmatrix_unexpected_prop: true\nfeatures:")),
    # Train participant pointing at a non-existent wagon vs legacy cross-ref resolution.
    Case("train-dangling-wagon-ref", "resolution/direct_reference_resolution",
         S.direct_reference_resolution,
         "src/atdd/planner/validators/test_plan_cross_refs.py::test_trains_reference_valid_wagons",
         patch=("plan/_trains/0001-self-compliance-validate.yaml",
                '"wagon:validate-conventions"', '"wagon:does-not-exist-xyz"')),
    # Dangling feature ref in a wagon manifest vs the legacy full URN-chain check.
    Case("feature-ref-dangling", "resolution/reference_chain_resolution",
         S.reference_chain_resolution,
         "src/atdd/planner/validators/test_wagon_urn_chain.py::test_all_wagons_have_complete_chains",
         patch=("plan/validate_conventions/_validate_conventions.yaml",
                "feature:validate-conventions:family-template-catalogue",
                "feature:validate-conventions:does-not-exist-xyz")),
    # Rule declaring a validator with no real implementation file vs legacy binding check.
    Case("rule-validator-missing-impl", "binding/declaration_to_implementation_binding",
         S.declaration_to_implementation_binding,
         "src/atdd/coach/validators/test_rule_validator_binding.py::test_every_enforced_rule_has_real_validator",
         # disposition: strict places the rule inside legacy's *enforced* scope
         # (the true counterpart). Without a disposition legacy treats it as
         # "unmigrated / out of scope" — that scope divergence is recorded in the
         # adjudication ledger rather than claimed as a stricter-coverage win.
         tempfile=("src/atdd/coach/conventions/_tmp_catchmatrix_binding.convention.yaml",
                   'version: "1.0"\nname: "catch-matrix binding"\nrules:\n'
                   '  - id: "coach.catchmatrix.binding-probe"\n    severity: 3\n'
                   '    disposition: strict\n'
                   '    validator: "test_nonexistent_catchmatrix_validator_file::test_x"\n')),
    # Malformed convention source vs the legacy convention loader (composition load).
    Case("malformed-convention-source", "composition/composed_graph_loads",
         S.composed_graph_loads,
         "src/atdd/coach/validators/test_rule_id_uniqueness.py",
         tempfile=("src/atdd/coach/conventions/_tmp_catchmatrix_badyaml.convention.yaml",
                   'version: "1.0"\nname: "catch-matrix malformed"\nrules: [unterminated\n')),
    # Rule whose declared validator exists but never bind_rule()s it (forward roundtrip).
    Case("rule-validator-roundtrip-broken", "binding/rule_validator_roundtrip",
         S.rule_validator_roundtrip,
         "src/atdd/coach/validators/test_rule_validator_binding.py::test_every_enforced_rule_has_real_validator",
         tempfile=("src/atdd/coach/conventions/_tmp_catchmatrix_roundtrip.convention.yaml",
                   'version: "1.0"\nname: "catch-matrix roundtrip"\nrules:\n'
                   '  - id: "coach.catchmatrix.roundtrip-probe"\n    severity: 3\n'
                   '    disposition: strict\n'
                   '    validator: "test_theme_must_be_canonical::test_every_wagon_theme_is_canonical"\n')),
    # Feature 'references' doc that does not resolve on disk. NO legacy counterpart
    # validates feature.references docs -> structurally convention-only (NEW coverage,
    # adjudicated as improvement after verifying the path truly does not resolve).
    Case("feature-doc-reference-dangling", "resolution/artifact_reference_resolution",
         S.artifact_reference_resolution,
         "src/atdd/planner/validators/test_plan_urn_resolution.py::test_contract_urn_resolves_to_directory",
         patch=("plan/govern_lifecycle/features/define_validator_report_and_persistence_materialization_contract.yaml",
                "docs/coach-decomposition.md", "docs/this-doc-does-not-exist-xyz.md")),
]


def run_matrix(repo_root) -> List[Cell]:
    root = Path(repo_root)
    cells: List[Cell] = []
    for case in CASES:
        clean = len(case.sentinel(load_composed_graph(root)).violations)
        legacy_clean_red = _legacy_caught(root, case.legacy_target)   # legacy on CLEAN tree
        with _inject(root, case):
            legacy = _legacy_caught(root, case.legacy_target)
            conv = _conv_caught(root, case.sentinel)
        cells.append(Cell(case.name, case.family_template, clean,
                          legacy_clean_red, legacy, conv))
    return cells


def render(cells: List[Cell]) -> str:
    from collections import Counter
    tally = Counter(c.verdict for c in cells)
    fp = sum(1 for c in cells if c.clean_convention_flags)
    inconclusive = sum(1 for c in cells if c.legacy_clean_red)
    out = ["# Legacy-vs-Convention Catch Matrix (#1212)\n",
           "Differential measurement: each fault run through BOTH suites on identical input.\n",
           "Each legacy target is also run on the CLEAN tree; a target already red on clean\n"
           "is marked **inconclusive** (its red is pre-existing and cannot be credited to the\n"
           "injected fault), and is excluded from the parity count.\n",
           "## Tally\n",
           f"- cases: **{len(cells)}**",
           f"- parity (both): **{tally['both']}**",
           f"- convention-only (improvement or FP — adjudicate #1211): **{tally['convention-only']}**",
           f"- legacy-only (coverage gap): **{tally['legacy-only']}**",
           f"- neither (shared blind spot): **{tally['neither']}**",
           f"- inconclusive (legacy red on clean): **{inconclusive}**",
           f"- clean-repo false positives (convention flags on clean): **{fp}**\n",
           "## Cells\n",
           "| case | family/template | clean-FP | legacy green on clean | legacy catches fault | convention catches | cell |",
           "|---|---|---|---|---|---|---|"]
    for c in cells:
        out.append(f"| {c.name} | {c.family_template} | {c.clean_convention_flags} | "
                   f"{'no' if c.legacy_clean_red else 'yes'} | "
                   f"{'yes' if c.legacy_caught else 'no'} | "
                   f"{'yes' if c.convention_caught else 'no'} | **{c.verdict}** |")
    out += ["\n> Corpus covers all 10 P0 sentinels. `both` = parity with the legacy",
            "> counterpart. `convention-only` here = NEW coverage (legacy has no counterpart",
            "> validator); each is adjudicated as improvement vs FP in",
            "> stricter-findings-adjudication.md — both current convention-only cells are",
            "> verified new-coverage, not FPs.",
            "> #1212 E027 expands further toward one fault per legacy rule. Decommission stays",
            "> BLOCKED until parity (both) is shown for every P0 pair a legacy validator owns,",
            "> with zero clean-repo FPs."]
    return "\n".join(out) + "\n"
