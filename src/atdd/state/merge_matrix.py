"""The merge-driver matrix — every ownership rule against every divergence case (#1400 C002).

A merge driver is only as trustworthy as the cells of its behaviour that someone actually
looked at. The dangerous shape is not a rule that is wrong; it is a rule that is *untested*
against one divergence case, because the first time that combination occurs it occurs during
a real merge, on a real branch, and whatever it does is what happens to the shared truth.

So the matrix is **data**: one cell per (declared merge rule × divergence case), each cell a
complete three-way scenario plus the outcome it must produce. Two things read it:

- ``state/tests/govern_projection_fields/test_c002_unit_002_*`` drives every cell through the
  real driver and asserts the cell's expectation — a merged document or a named conflict,
  never a pass that asserted nothing;
- :func:`check_coverage` enumerates the rules the *committed policy* declares against the
  four divergence cases and fails on any cell nobody wrote. Declaring a new merge rule in
  the policy therefore *makes the matrix incomplete* until its four cells exist, which is
  the property that keeps the driver's coverage from rotting as the policy grows.

The four divergence cases (spec §7.2, and the fourth is everything else):

===================  =========================================================
``identical``        both sides made the same change.
``no-op``            exactly one side changed anything.
``evidence-backed``  both sides changed, and the further side carries the gate
                     evidence the §6 model demands.
``unsafe``           both sides changed, and nothing justifies choosing between.
===================  =========================================================

Note what the matrix asserts about ``evidence-backed`` *outside* the phase ladder: evidence
buys nothing. A body, a slug or a train that two writers set to different values does not
become mergeable because the commit that carried it was well-evidenced — evidence is a
statement about a lifecycle gate, not about which of two strings is right.

Dependency discipline: stdlib + ``atdd.state`` only. No provider.
"""
from __future__ import annotations

from dataclasses import dataclass, field as dc_field
from typing import Any, Dict, FrozenSet, List, Optional, Sequence, Tuple

from atdd.state.merge_driver import (
    CASE_EVIDENCE_BACKED,
    CASE_IDENTICAL,
    CASE_NO_OP,
    CASE_UNSAFE,
    DIVERGENCE_CASES,
    canonical_list,
)
from atdd.state.ownership import (
    RULE_BOT_ONLY,
    RULE_DERIVED,
    RULE_IMMUTABLE,
    RULE_MONOTONIC_GATED,
    RULE_MUTABLE,
    RULE_POLICY_MERGE,
    RULE_SAME_DIGEST,
    RULE_SINGLE_OWNER,
    FieldOwnershipPolicy,
    default_policy,
)

#: The outcomes a cell may assert. A cell asserting neither is an unasserted pass, which the
#: coverage check treats as a hole rather than as a cell.
EXPECT_MERGED = "merged"
EXPECT_CONFLICT = "conflict"

#: Pinned identity, so the matrix's scenarios never move between runs.
UID = "wi_01HF7YAT00M78607F00000MTX1"

#: The evidence a jump from PLANNED to GREEN must carry: both gates it passes through
#: (PLANNED->RED and RED->GREEN), per the §6 evidence table.
FULL_EVIDENCE: FrozenSet[str] = frozenset({
    "operator_token_digest", "gate_id", "failing_test_evidence",
    "passing_test_evidence", "implementation_diff",
})

#: A pinned, obviously-fake digest for a value that only has to be well-formed.
_DIGEST = "sha256:" + "ab" * 32
_OTHER_DIGEST = "sha256:" + "cd" * 32


def document(**overrides: Any) -> Dict[str, Any]:
    """A valid ``commons:projection-object`` — the matrix's common ancestor."""
    doc: Dict[str, Any] = {
        "uid": UID,
        "slug": "feature-x",
        "phase": "PLANNED",
        "state": "ACTIVE",
        "owner_actor": "dev-a",
    }
    doc.update(overrides)
    return doc


@dataclass(frozen=True)
class Cell:
    """One (rule, case) scenario and the outcome the driver must produce for it."""

    rule: str
    case: str
    expect: str
    field: str
    base: Dict[str, Any]
    ours: Dict[str, Any]
    theirs: Dict[str, Any]
    ours_evidence: FrozenSet[str] = frozenset()
    theirs_evidence: FrozenSet[str] = frozenset()
    #: For a merged cell: the value the field must carry afterwards.
    merged_value: Any = None
    #: Why this cell is the interesting one — read by a human, not by the check.
    note: str = ""

    @property
    def key(self) -> Tuple[str, str]:
        return (self.rule, self.case)


def _cells() -> List[Cell]:
    """The matrix: eight rules, four cases, thirty-two scenarios."""
    cells: List[Cell] = []

    # ---- immutable (uid) — identity is minted once; no writer and no evidence rewrites it.
    base = document()
    cells += [
        Cell(RULE_IMMUTABLE, CASE_IDENTICAL, EXPECT_MERGED, "uid",
             base, document(), document(), merged_value=UID,
             note="neither side touched identity; the uid is carried through"),
        Cell(RULE_IMMUTABLE, CASE_NO_OP, EXPECT_CONFLICT, "uid",
             base, document(uid="wi_01HF7YAT00M78607F00000MTX9"), document(),
             note="one side rewrote the uid; immutable means no writer may, not even alone"),
        Cell(RULE_IMMUTABLE, CASE_EVIDENCE_BACKED, EXPECT_CONFLICT, "uid",
             base, document(uid="wi_01HF7YAT00M78607F00000MTX9"), document(),
             ours_evidence=FULL_EVIDENCE, theirs_evidence=FULL_EVIDENCE,
             note="no amount of gate evidence buys a rewrite of identity"),
        Cell(RULE_IMMUTABLE, CASE_UNSAFE, EXPECT_CONFLICT, "uid",
             base, document(uid="wi_01HF7YAT00M78607F00000MTX9"),
             document(uid="wi_01HF7YAT00M78607F00000MTX8"),
             note="both sides rewrote identity, differently"),
    ]

    # ---- mutable (slug) — display metadata: one mover merges, two movers conflict.
    cells += [
        Cell(RULE_MUTABLE, CASE_IDENTICAL, EXPECT_MERGED, "slug",
             base, document(slug="renamed"), document(slug="renamed"), merged_value="renamed",
             note="both sides renamed it the same way"),
        Cell(RULE_MUTABLE, CASE_NO_OP, EXPECT_MERGED, "slug",
             base, document(slug="renamed"), document(), merged_value="renamed",
             note="only one side renamed it"),
        Cell(RULE_MUTABLE, CASE_EVIDENCE_BACKED, EXPECT_CONFLICT, "slug",
             base, document(slug="renamed-ours"), document(slug="renamed-theirs"),
             ours_evidence=FULL_EVIDENCE, theirs_evidence=FULL_EVIDENCE,
             note="evidence is about lifecycle gates; it cannot say which of two names is right"),
        Cell(RULE_MUTABLE, CASE_UNSAFE, EXPECT_CONFLICT, "slug",
             base, document(slug="renamed-ours"), document(slug="renamed-theirs"),
             note="two writers renamed one object differently"),
    ]

    # ---- monotonic-gated (phase) — the three §7.2 safe cases live here, and nowhere else.
    cells += [
        Cell(RULE_MONOTONIC_GATED, CASE_IDENTICAL, EXPECT_MERGED, "phase",
             base, document(phase="RED"), document(phase="RED"),
             ours_evidence=FULL_EVIDENCE, theirs_evidence=FULL_EVIDENCE, merged_value="RED",
             note="§7.2 case 1: the transitions are identical"),
        Cell(RULE_MONOTONIC_GATED, CASE_NO_OP, EXPECT_MERGED, "phase",
             base, document(phase="RED"), document(),
             ours_evidence=FULL_EVIDENCE, merged_value="RED",
             note="§7.2 case 2: one side is a strict no-op"),
        Cell(RULE_MONOTONIC_GATED, CASE_EVIDENCE_BACKED, EXPECT_MERGED, "phase",
             base, document(phase="RED"), document(phase="GREEN"),
             ours_evidence=FULL_EVIDENCE, theirs_evidence=FULL_EVIDENCE, merged_value="GREEN",
             note="§7.2 case 3: the further phase carries evidence for every skipped gate"),
        Cell(RULE_MONOTONIC_GATED, CASE_UNSAFE, EXPECT_CONFLICT, "phase",
             base, document(phase="RED"), document(phase="GREEN"),
             ours_evidence=FULL_EVIDENCE,
             note="the further phase skipped PLANNED->RED with no evidence: never blind max phase"),
    ]

    # ---- conflict-unless-single-owner (body) — two writers, one body, no merge.
    with_body = document(body="the original body")
    cells += [
        Cell(RULE_SINGLE_OWNER, CASE_IDENTICAL, EXPECT_MERGED, "body",
             with_body, document(body="rewritten"), document(body="rewritten"),
             merged_value="rewritten",
             note="both sides wrote the same text; there is nothing to choose between"),
        Cell(RULE_SINGLE_OWNER, CASE_NO_OP, EXPECT_MERGED, "body",
             with_body, document(body="rewritten"), document(body="the original body"),
             merged_value="rewritten",
             note="the object's single owner moved it and the other side did not"),
        Cell(RULE_SINGLE_OWNER, CASE_EVIDENCE_BACKED, EXPECT_CONFLICT, "body",
             with_body, document(body="ours"), document(body="theirs"),
             ours_evidence=FULL_EVIDENCE, theirs_evidence=FULL_EVIDENCE,
             note="a well-evidenced commit still cannot merge two prose rewrites"),
        Cell(RULE_SINGLE_OWNER, CASE_UNSAFE, EXPECT_CONFLICT, "body",
             with_body, document(body="ours", owner_actor="dev-a"),
             document(body="theirs", owner_actor="dev-b"),
             note="two owners rewrote one body: the single-owner rule cannot prove either safe"),
    ]

    # ---- conflict-unless-same-digest (train).
    cells += [
        Cell(RULE_SAME_DIGEST, CASE_IDENTICAL, EXPECT_MERGED, "train",
             base, document(train="train:commons:spine"), document(train="train:commons:spine"),
             merged_value="train:commons:spine",
             note="the two sides carry the same train: the same digest"),
        Cell(RULE_SAME_DIGEST, CASE_NO_OP, EXPECT_MERGED, "train",
             base, document(train="train:commons:spine"), document(),
             merged_value="train:commons:spine",
             note="only one side set the train"),
        Cell(RULE_SAME_DIGEST, CASE_EVIDENCE_BACKED, EXPECT_CONFLICT, "train",
             base, document(train="train:commons:spine"), document(train="train:commons:other"),
             ours_evidence=FULL_EVIDENCE, theirs_evidence=FULL_EVIDENCE,
             note="different digests are different digests, however well-evidenced the commit"),
        Cell(RULE_SAME_DIGEST, CASE_UNSAFE, EXPECT_CONFLICT, "train",
             base, document(train="train:commons:spine"), document(train="train:commons:other"),
             note="two sides put the object on different trains"),
    ]

    # ---- policy-merge (wmbts) — disjoint additions union; a contradicted entry conflicts.
    wmbt_a = {"urn": "wmbt:commons:A", "statement": "minimize X"}
    wmbt_b = {"urn": "wmbt:commons:B", "statement": "maximize Y"}
    wmbt_a_edited = {"urn": "wmbt:commons:A", "statement": "minimize Z"}
    cells += [
        Cell(RULE_POLICY_MERGE, CASE_IDENTICAL, EXPECT_MERGED, "wmbts",
             base, document(wmbts=[wmbt_a]), document(wmbts=[wmbt_a]), merged_value=[wmbt_a],
             note="both sides attached the same WMBT"),
        Cell(RULE_POLICY_MERGE, CASE_NO_OP, EXPECT_MERGED, "wmbts",
             base, document(wmbts=[wmbt_a]), document(), merged_value=[wmbt_a],
             note="only one side attached a WMBT"),
        Cell(RULE_POLICY_MERGE, CASE_EVIDENCE_BACKED, EXPECT_MERGED, "wmbts",
             base, document(wmbts=[wmbt_a]), document(wmbts=[wmbt_b]),
             ours_evidence=FULL_EVIDENCE, theirs_evidence=FULL_EVIDENCE,
             merged_value=canonical_list([wmbt_a, wmbt_b]),
             note="disjoint additions union — in the projector's canonical (content) order, "
                  "so the merged object is still byte-identical to the projection of the "
                  "merged state"),
        Cell(RULE_POLICY_MERGE, CASE_UNSAFE, EXPECT_CONFLICT, "wmbts",
             document(wmbts=[wmbt_a]), document(wmbts=[wmbt_a_edited]), document(wmbts=[wmbt_b]),
             note="one side rewrote a WMBT the other side kept: contradiction, not addition"),
    ]

    # ---- derived (extension_digests) — core writes it, the provider supplies it.
    cells += [
        Cell(RULE_DERIVED, CASE_IDENTICAL, EXPECT_MERGED, "extension_digests",
             base, document(extension_digests={"github": _DIGEST}),
             document(extension_digests={"github": _DIGEST}),
             merged_value={"github": _DIGEST},
             note="both sides derived the same digest from the same lock"),
        Cell(RULE_DERIVED, CASE_NO_OP, EXPECT_MERGED, "extension_digests",
             base, document(extension_digests={"github": _DIGEST}), document(),
             merged_value={"github": _DIGEST},
             note="only one side recorded a provider digest"),
        Cell(RULE_DERIVED, CASE_EVIDENCE_BACKED, EXPECT_MERGED, "extension_digests",
             base, document(extension_digests={"github": _DIGEST}),
             document(extension_digests={"gitlab": _OTHER_DIGEST}),
             ours_evidence=FULL_EVIDENCE, theirs_evidence=FULL_EVIDENCE,
             merged_value={"github": _DIGEST, "gitlab": _OTHER_DIGEST},
             note="two providers, two disjoint keys: the union is the only reading"),
        Cell(RULE_DERIVED, CASE_UNSAFE, EXPECT_CONFLICT, "extension_digests",
             base, document(extension_digests={"github": _DIGEST}),
             document(extension_digests={"github": _OTHER_DIGEST}),
             note="one provider, two digests: one of the two locks is stale"),
    ]

    # ---- bot-only (external_refs) — non-authoritative, which is not the same as arbitrary.
    ours_ref = {"github": {"issue_number": 1400}}
    theirs_ref = {"gitlab": {"issue_iid": 77}}
    clash_ref = {"github": {"issue_number": 1401}}
    cells += [
        Cell(RULE_BOT_ONLY, CASE_IDENTICAL, EXPECT_MERGED, "external_refs",
             base, document(external_refs=ours_ref), document(external_refs=ours_ref),
             merged_value=ours_ref,
             note="the bot wrote the same ref on both sides"),
        Cell(RULE_BOT_ONLY, CASE_NO_OP, EXPECT_MERGED, "external_refs",
             base, document(external_refs=ours_ref), document(), merged_value=ours_ref,
             note="the bot mirrored on one side only"),
        Cell(RULE_BOT_ONLY, CASE_EVIDENCE_BACKED, EXPECT_MERGED, "external_refs",
             base, document(external_refs=ours_ref), document(external_refs=theirs_ref),
             ours_evidence=FULL_EVIDENCE, theirs_evidence=FULL_EVIDENCE,
             merged_value={**ours_ref, **theirs_ref},
             note="two providers' subtrees are disjoint and union cleanly"),
        Cell(RULE_BOT_ONLY, CASE_UNSAFE, EXPECT_CONFLICT, "external_refs",
             base, document(external_refs=ours_ref), document(external_refs=clash_ref),
             note="one provider, two issue numbers: non-authoritative is not 'pick one'"),
    ]

    return cells


#: The matrix. Built once, read by the driver's acceptance test and by the coverage check.
MATRIX: Tuple[Cell, ...] = tuple(_cells())


def cells_by_key(cells: Sequence[Cell] = MATRIX) -> Dict[Tuple[str, str], List[Cell]]:
    """The matrix indexed by ``(rule, case)``."""
    index: Dict[Tuple[str, str], List[Cell]] = {}
    for cell in cells:
        index.setdefault(cell.key, []).append(cell)
    return index


@dataclass(frozen=True)
class MatrixReport:
    """The outcome of checking the matrix against the policy's declared rules (C002)."""

    rules: Tuple[str, ...]
    cases: Tuple[str, ...]
    exercised: int = 0
    missing: List[Tuple[str, str]] = dc_field(default_factory=list)
    unasserted: List[Tuple[str, str]] = dc_field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.rules) * len(self.cases)

    @property
    def ok(self) -> bool:
        return not self.missing and not self.unasserted

    def render(self) -> str:
        if self.ok:
            return (
                f"the merge-driver matrix exercises every cell "
                f"({self.exercised}/{self.total}: {len(self.rules)} rule(s) × "
                f"{len(self.cases)} divergence case(s))"
            )
        lines = [
            f"merge-matrix blind spot(s) ({len(self.missing) + len(self.unasserted)} cell(s) of "
            f"{self.total}):"
        ]
        for rule, case in self.missing:
            lines.append(
                f"  - {rule} × {case}: unexercised — no cell drives this combination, so a "
                "regression in it would go undetected"
            )
        for rule, case in self.unasserted:
            lines.append(
                f"  - {rule} × {case}: exercised but asserts nothing; a cell must expect "
                f"{EXPECT_MERGED!r} or {EXPECT_CONFLICT!r}"
            )
        return "\n".join(lines)


def check_coverage(
    cells: Sequence[Cell] = MATRIX,
    *,
    policy: Optional[FieldOwnershipPolicy] = None,
    cases: Sequence[str] = DIVERGENCE_CASES,
) -> MatrixReport:
    """Every merge rule the policy declares, against every divergence case (C002).

    The rule set comes from the **policy**, not from the matrix: a matrix that is complete
    with respect to itself is complete by construction and proves nothing. Declaring a new
    rule is what creates the four holes this check then refuses to ignore.
    """
    policy = policy or default_policy()
    rules = policy.rules()
    index = cells_by_key(cells)
    missing: List[Tuple[str, str]] = []
    unasserted: List[Tuple[str, str]] = []
    exercised = 0
    for rule in rules:
        for case in cases:
            found = index.get((rule, case), [])
            if not found:
                missing.append((rule, case))
                continue
            if any(cell.expect not in (EXPECT_MERGED, EXPECT_CONFLICT) for cell in found):
                unasserted.append((rule, case))
                continue
            exercised += 1
    return MatrixReport(
        rules=tuple(rules),
        cases=tuple(cases),
        exercised=exercised,
        missing=missing,
        unasserted=unasserted,
    )
