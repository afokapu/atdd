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
    legacy_caught: bool
    convention_caught: bool
    verdict: str = field(init=False)

    def __post_init__(self):
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
]


def run_matrix(repo_root) -> List[Cell]:
    root = Path(repo_root)
    cells: List[Cell] = []
    for case in CASES:
        clean = len(case.sentinel(load_composed_graph(root)).violations)
        with _inject(root, case):
            legacy = _legacy_caught(root, case.legacy_target)
            conv = _conv_caught(root, case.sentinel)
        cells.append(Cell(case.name, case.family_template, clean, legacy, conv))
    return cells


def render(cells: List[Cell]) -> str:
    from collections import Counter
    tally = Counter(c.verdict for c in cells)
    fp = sum(1 for c in cells if c.clean_convention_flags)
    out = ["# Legacy-vs-Convention Catch Matrix (#1212)\n",
           "Differential measurement: each fault run through BOTH suites on identical input.\n",
           "## Tally\n",
           f"- cases: **{len(cells)}**",
           f"- parity (both): **{tally['both']}**",
           f"- convention-only (improvement or FP — adjudicate #1211): **{tally['convention-only']}**",
           f"- legacy-only (coverage gap): **{tally['legacy-only']}**",
           f"- neither (shared blind spot): **{tally['neither']}**",
           f"- clean-repo false positives (convention flags on clean): **{fp}**\n",
           "## Cells\n",
           "| case | family/template | clean-FP | legacy catches | convention catches | cell |",
           "|---|---|---|---|---|---|"]
    for c in cells:
        out.append(f"| {c.name} | {c.family_template} | {c.clean_convention_flags} | "
                   f"{'yes' if c.legacy_caught else 'no'} | "
                   f"{'yes' if c.convention_caught else 'no'} | **{c.verdict}** |")
    out += ["\n> Corpus is seeded for cases with a legacy counterpart + injectable fault.",
            "> #1212 E027 expands to one fault per legacy rule. Decommission stays BLOCKED",
            "> until parity (both) is shown for every P0 pair with zero clean-repo FPs."]
    return "\n".join(out) + "\n"
