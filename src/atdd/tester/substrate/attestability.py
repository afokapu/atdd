"""Classify whether a SMOKE acceptance can produce a live-smoke attestation (#1664).

The obligation must be derivable, not declared. #1609 tried to close the
opt-out-by-omission hole by requiring authors to write ``execution_kind`` on the
acceptance; that is self-attestation, and its own feature file demonstrated the
escape by declaring ``components.backend.integration: count: 0`` with the note
"this zero is what makes C011 inapplicable to its own feature". Nothing anywhere
validates a declared ``execution_kind`` against reality.

So this module derives instead, on two independent axes that #1664's original
scope conflated into one.

**Axis 1 — is the obligation owed?** Every acceptance URN is
``acc:<wagon>:<CODE>-SMOKE-NNN`` and ``plan/_trains.yaml`` names each train's
``wagons[]``, so membership is a set test on a gate-enforced input: the phase
machine already refuses to leave PLANNED without a train lineage
(``issue.py``, "implementation-type issues require lineage to a Train past
PLANNED"). Measured on main, 328 of 328 SMOKE acceptances belong to a wagon that
is in a train, so the "not in a train" branch is currently empty rather than rare.

**Axis 2 — can it be discharged as invoked?** Attestation is recorded by the
``atdd_substrate`` pytest11 entry point (``pyproject.toml`` →
``atdd.tester.substrate.plugin``). Entry-point discovery reads the installed
dist-info, so ``PYTHONPATH=src python3 -m pytest`` loads the code but NOT the
plugin, and the tests pass identically either way. CI carries 13 such
invocations — every validator job — against one job that installs the package
specifically to prove the hook can fire, whose own comment says removing the
install "does not slow the job down, it silently unloads the hook".

Attestability is therefore a property of the invocation as much as the
acceptance, and a classifier that reports only the acceptance would be reporting
half the answer.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set

#: ``acc:<wagon>:<CODE>-SMOKE-NNN`` — the wagon is capture group 1.
SMOKE_URN = re.compile(r"^acc:([a-z0-9-]+):([A-Z]\d+-SMOKE-\d+)")

#: The test-header layer that means "this test is a smoke test".
SMOKE_LAYER = "smoke"

CAN_ATTEST = "can-attest-today"
SHOULD_DECLARE = "should-declare"
NEVER_ATTESTABLE = "never-attestable-by-construction"
UNRESOLVED = "unresolved"


@dataclass(frozen=True)
class Attestability:
    """One SMOKE acceptance's derived classification.

    ``urn`` / ``wagon`` come from the acceptance itself; ``in_train`` is axis 1;
    ``test_files`` and ``layer`` are the evidence for axis 2. ``klass`` is the
    single class this acceptance resolves to, and ``unresolved`` is never
    auto-discharged — it routes to adjudication and never counts as coverage.
    """

    urn: str
    wagon: str
    in_train: bool
    test_files: List[Path]
    layer: Optional[str]
    klass: str
    reason: str


def train_wagons(trains_doc: dict) -> Set[str]:
    """Every wagon named by any train in a parsed ``plan/_trains.yaml``.

    The document nests ``trains -> <group> -> <category> -> [train, ...]``, and
    a train names its wagons in ``wagons[]``. Groups and categories are opaque
    here: membership is what matters, not which train confers it.
    """
    wagons: Set[str] = set()
    for group in (trains_doc.get("trains") or {}).values():
        if not isinstance(group, dict):
            continue
        for entries in group.values():
            for entry in entries or []:
                if isinstance(entry, dict):
                    wagons.update(entry.get("wagons") or [])
    return wagons


def classify(
    urn: str,
    wagons_in_trains: Set[str],
    headers: Dict[str, List[Path]],
    layers: Dict[Path, Optional[str]],
) -> Optional[Attestability]:
    """Derive one acceptance's class, or ``None`` if the URN is not a SMOKE one.

    Pure: every input is already-loaded data, so the whole classification is
    testable from synthetic dicts with no repo walk.
    """
    m = SMOKE_URN.match(urn)
    if not m:
        return None
    wagon = m.group(1)
    in_train = wagon in wagons_in_trains
    tests = list(headers.get(urn) or [])

    if not tests:
        return Attestability(
            urn, wagon, in_train, [], None, UNRESOLVED,
            "no test anchors this acceptance, so nothing can attest it",
        )

    test_layers = [layers.get(t) for t in tests]
    if any(layer == SMOKE_LAYER for layer in test_layers):
        return Attestability(
            urn, wagon, in_train, tests, SMOKE_LAYER, CAN_ATTEST,
            "anchored by a Layer: smoke test",
        )
    if all(layer is None for layer in test_layers):
        return Attestability(
            urn, wagon, in_train, tests, None, UNRESOLVED,
            "anchored test carries no Layer: header, so its runtime is unknown",
        )

    declared = next(layer for layer in test_layers if layer is not None)
    if not in_train:
        return Attestability(
            urn, wagon, in_train, tests, declared, NEVER_ATTESTABLE,
            f"wagon {wagon!r} is in no train, so no interlocking runtime reaches it",
        )
    return Attestability(
        urn, wagon, in_train, tests, declared, SHOULD_DECLARE,
        f"in a train but anchored only by Layer: {declared} — claims SMOKE, is not one",
    )


# --------------------------------------------------------------------------- #
# Axis 3: is the anchored test on a path CI actually runs, under a runner that
# loads the plugin? (#1664 team finding, 2026-09-07)
#
# THIS CLASSIFIER NEVER RUNS A TEST. Attestation is written by a pytest11 entry
# point, so a classifier that executed tests to decide capability would classify
# its own runner rather than the acceptance: the same test writes an attestation
# under the installed dist and writes none under `PYTHONPATH=src`, and BOTH
# report passed. Every input here is static — workflow text and file paths.
# --------------------------------------------------------------------------- #

#: A CI step that runs pytest against a path under src/.
_CI_PYTEST_TARGET = re.compile(r"pytest\s+((?:src|tests)/[A-Za-z0-9_./-]*)")

#: A job boundary in a workflow file: a two-space-indented key under `jobs:`.
_JOB_HEADER = re.compile(r"\n  (?=[A-Za-z0-9_-]+:\n)")

#: A CI step that installs the distribution, which is what writes the dist-info
#: pytest's entry-point discovery reads. `PYTHONPATH=src` never does.
_CI_INSTALLS_DIST = re.compile(r"pip3?\s+install[^\n]*(-e\s+\.|dist/\*\.whl|\.\[)")


def ci_pytest_targets(workflow_texts: Dict[str, str]) -> Dict[str, bool]:
    """Map each CI pytest target path to whether its job installs the dist.

    A target whose job never installs the package cannot load the attestation
    plugin, so a test under it produces no evidence however green it runs.
    """
    targets: Dict[str, bool] = {}
    for text in workflow_texts.values():
        # Split per JOB, not per step: the install and the pytest call are
        # different steps of the same job, so a per-step split would report the
        # one job that installs as though it did not.
        for block in _JOB_HEADER.split(text):
            installs = bool(_CI_INSTALLS_DIST.search(block))
            for m in _CI_PYTEST_TARGET.finditer(block):
                path = m.group(1).rstrip("/")
                targets[path] = targets.get(path, False) or installs
    return targets


def attesting_ci_path(test_file: Path, targets: Dict[str, bool]) -> Optional[bool]:
    """True if *test_file* sits under a CI target whose job installs the dist.

    ``False`` means CI runs it but cannot record; ``None`` means CI does not run
    it at all — the case that is invisible in a green build and the reason
    ``src/atdd/substrate/tests/`` produces nothing despite passing locally.
    """
    posix = test_file.as_posix()
    covered = [(t, ins) for t, ins in targets.items() if posix.startswith(t.rstrip("/") + "/")]
    if not covered:
        return None
    return any(ins for _, ins in covered)


# --------------------------------------------------------------------------- #
# Census annotation (#1664): add the derived columns to docs/smoke-audit.md and
# close the gate's open direction.
#
# `acc:govern-lifecycle:E027-SMOKE-001` asserts every plan acceptance has a row,
# but never the converse, so the table accumulates rows for URNs `plan/` no
# longer declares. Those are reported here rather than silently rewritten: a row
# whose acceptance is gone is a claim about nothing, and deleting it quietly
# would destroy the only record that it once existed.
# --------------------------------------------------------------------------- #

_HEADER_SEP = re.compile(r"^\|[\s:|-]+\|$")

CENSUS_COLUMNS = ("live-smoke-attestability", "ci-runner")


def _row_urn(line: str) -> Optional[str]:
    """The acceptance URN a census row is keyed by, if the line is a data row."""
    if not line.startswith("|") or _HEADER_SEP.match(line.strip()):
        return None
    first = line.split("|")[1].strip()
    return first if first.startswith("acc:") else None


def annotate_census(
    census_text: str,
    klass_by_urn: Dict[str, str],
    runner_by_urn: Dict[str, str],
) -> "tuple[str, List[str], List[str]]":
    """Add the derived columns to the census table.

    Returns ``(new_text, stale_urns, missing_urns)`` — rows whose acceptance no
    longer exists in ``plan/``, and acceptances with no row. Neither is repaired
    here; both are reported so the closing direction becomes visible.
    """
    out: List[str] = []
    stale: List[str] = []
    seen: Set[str] = set()
    header_done = False

    for line in census_text.splitlines():
        stripped = line.rstrip()
        if not header_done and stripped.startswith("| acceptance-URN"):
            out.append(stripped.rstrip("|").rstrip() + " | " + " | ".join(CENSUS_COLUMNS) + " |")
            continue
        if not header_done and _HEADER_SEP.match(stripped):
            out.append(stripped.rstrip("|").rstrip() + " | " + " | ".join("---" for _ in CENSUS_COLUMNS) + " |")
            header_done = True
            continue
        urn = _row_urn(stripped)
        if urn is None:
            out.append(stripped)
            continue
        seen.add(urn)
        if urn not in klass_by_urn:
            stale.append(urn)
            out.append(stripped.rstrip("|").rstrip() + " | (stale — no such acceptance in plan/) | — |")
            continue
        out.append(
            stripped.rstrip("|").rstrip()
            + f" | {klass_by_urn[urn]} | {runner_by_urn.get(urn, 'unknown')} |"
        )

    missing = sorted(u for u in klass_by_urn if u not in seen)
    return "\n".join(out) + "\n", sorted(stale), missing
