"""``atdd coach reconcile-state`` — the lifecycle repair verb (#1338).

WHAT THIS REPAIRS
    ``atdd:<PHASE>`` is a *projection* of ``objects.state``. #1452 stopped the
    bleeding — it deleted the raw ``gh issue edit`` phase-label writes from
    ``post-merge-lifecycle.yml`` and inverted ``IssueManager.update`` so the
    store moves before the label rendered from it. But the wound it was
    treating was already there. Measured on the live repo 2026-07-13:

        label == store  185 (44%)
        label != store  236 (56%)

    217 of those 236 carry ONE signature — ``label=COMPLETE`` with the store
    parked at the last phase legitimately driven through the phase machine
    (INIT 82, REFACTOR 61, SMOKE 34, GREEN 21, PLANNED 19).

THE FRAMING THAT GOVERNS EVERY LINE BELOW
    **The store is not corrupt — it is honest and stale. The LABEL is the
    unearned one.** ``objects.state`` records the last phase actually driven;
    the label was stamped by a workflow that consulted nothing. So the repair
    treats the store as the survivor and the label as the artifact to
    re-derive. It is emphatically NOT ``store := label`` — that would launder
    the corruption into the source of truth.

WHY A NEW VERB WAS NEEDED AT ALL
    Every existing verb reads the corrupted label and refuses, or is scoped to
    backfill:

    - ``atdd coach transition <N> COMPLETE`` reads the label, sees COMPLETE and
      refuses (``Cannot transition from COMPLETE to COMPLETE``) — the corrupted
      label blocks its own repair.
    - ``atdd auto-phase <pr>`` no-ops (``phase COMPLETE has no auto-advance``).
    - ``atdd coach reconcile`` backfills issues *missing* from the store;
      "existing entries are left untouched". It reconciles existence, never
      state.
    - ``atdd coach sync-labels`` re-derives labels from the issue **body**, not
      from the store — a different source, and not the authoritative one.

WHAT EVIDENCE EXISTS (and what does not)
    ``objects.state``          — trustworthy FLOOR; the last *earned* phase.
    closed by a **merged** PR  — proves the work actually landed.
    the ``atdd:<PHASE>`` label — SUSPECT; this is the corrupted artifact, the
                                 input to the bug, not evidence.
    the ``events`` table       — carries NO phase transitions (only
                                 ``version_bumped``, ``issue_revised``,
                                 ``spawned``, ``prompt_sent``). ``objects.state``
                                 is a mutable column, not event-sourced.

    So the verb **cannot reconstruct history**. It reasons from the floor plus
    merge evidence. That limitation is what makes class 4 a refusal.

Convention: src/atdd/coach/conventions/issue.convention.yaml
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Set

# The linear lifecycle spine, from
# ``src/atdd/coach/conventions/phase_machine.convention.yaml``. Only the
# forward single-step edges are replayable; BLOCKED/OBSOLETE are escapes and are
# never synthesised by a repair.
PHASE_ORDER: Sequence[str] = (
    "INIT", "PLANNED", "RED", "GREEN", "SMOKE", "REFACTOR", "COMPLETE",
)

# Phases that carry no position on the spine. A record sitting on one of these
# has no "missing steps" to replay, so the repair can only re-project.
OFF_SPINE = frozenset({"BLOCKED", "OBSOLETE", "UNKNOWN"})

# Repair-class identifiers. Kept as ints to match the issue's table.
CLASS_IN_SYNC = 0
CLASS_PROJECTION_LAG = 1
CLASS_UNEARNED_WORK_LANDED = 2
CLASS_UNEARNED_NO_EVIDENCE = 3
CLASS_LEGACY_UNDRIVEN = 4
CLASS_UNKNOWN_TO_STORE = 5

CLASS_NAMES: Dict[int, str] = {
    CLASS_IN_SYNC: "in-sync",
    CLASS_PROJECTION_LAG: "projection-lag",
    CLASS_UNEARNED_WORK_LANDED: "unearned-label, work landed",
    CLASS_UNEARNED_NO_EVIDENCE: "unearned-label, no merge evidence",
    CLASS_LEGACY_UNDRIVEN: "legacy-undriven",
    CLASS_UNKNOWN_TO_STORE: "unknown to the store",
}


@dataclass(frozen=True)
class Repair:
    """The classification of one record, and the remedy it selects.

    ``transitions`` are the phases to drive through ``IssueManager.update``,
    in order, one legal single step at a time. ``reproject_to`` is the phase to
    re-render the label at without moving the store. They are mutually
    exclusive: a repair either advances the store legally or re-derives the
    projection — never both, and never a direct ``objects.state`` write.
    """

    issue_number: int
    label_phase: Optional[str]
    store_phase: Optional[str]
    merged: bool
    repair_class: int
    reason: str
    transitions: tuple = ()
    reproject_to: Optional[str] = None
    refused: bool = False

    @property
    def class_name(self) -> str:
        return CLASS_NAMES.get(self.repair_class, "unclassified")

    @property
    def is_noop(self) -> bool:
        return not self.transitions and self.reproject_to is None


def _spine_index(phase: Optional[str]) -> Optional[int]:
    """Position on the lifecycle spine, or None for an off-spine/unknown phase.

    A membership test rather than a caught ``ValueError``: off-spine is an
    ordinary answer here (BLOCKED, OBSOLETE and UNKNOWN are all legitimate
    phases with no position), not an exceptional one.
    """
    if not phase:
        return None
    upper = phase.upper()
    if upper not in PHASE_ORDER:
        return None
    return PHASE_ORDER.index(upper)


def missing_steps(store_phase: str, target_phase: str) -> tuple:
    """The legal single-step phases from ``store_phase`` up to ``target_phase``.

    ``missing_steps("SMOKE", "COMPLETE") -> ("REFACTOR", "COMPLETE")`` — each
    one a real edge in the phase machine, so each replayed transition is
    validated and recorded exactly like an operator-driven one. Empty when the
    store is already at or beyond the target, or when either phase is off-spine.
    """
    start, end = _spine_index(store_phase), _spine_index(target_phase)
    if start is None or end is None or end <= start:
        return ()
    return tuple(PHASE_ORDER[start + 1:end + 1])


def classify(
    issue_number: int,
    label_phase: Optional[str],
    store_phase: Optional[str],
    merged: bool,
) -> Repair:
    """Pure classification of one record into its repair class.

    Pure — no I/O, no store, no GitHub — so the classes can be exercised
    exhaustively and a class-4 refusal can be fault-injected and *watched to
    fire*. A guard that cannot be shown to fail is a stub.

    Class order is load-bearing. Class 4 is tested BEFORE class 2: a record with
    ``store=INIT`` and ``label=COMPLETE`` would otherwise qualify for a six-step
    replay, and that replay is exactly the fabrication the refusal exists to
    prevent.
    """
    label = (label_phase or "").upper() or None
    store = (store_phase or "").upper() or None

    # The store does not know this record. Not drift — absence. Backfilling it
    # is `atdd coach reconcile`'s job, and guessing a phase from the suspect
    # label here is how the corruption would get laundered into the store.
    if store is None:
        return Repair(
            issue_number, label, store, merged, CLASS_UNKNOWN_TO_STORE,
            reason=(
                "the State Store has no work item for this issue, so there is "
                "no floor to reason from. Run `atdd coach reconcile` to backfill "
                "it first; this verb repairs state, never existence."
            ),
        )

    if label == store:
        return Repair(
            issue_number, label, store, merged, CLASS_IN_SYNC,
            reason="label already projects the store",
        )

    # ---- Class 4: legacy-undriven. REFUSE. -------------------------------
    #
    # store=INIT with the label claiming COMPLETE. The store floor is INIT not
    # because the bug caught this record at INIT, but because the store was
    # never driven for it at all — it was backfilled at INIT by `reconcile` and
    # predates store-first writes. 82 records carry this shape.
    #
    # Replaying INIT -> PLANNED -> RED -> GREEN -> SMOKE -> REFACTOR -> COMPLETE
    # for them would fabricate an audit trail that never happened. That is
    # WORSE than the drift it replaces: it trades a *wrong* record for a
    # *fraudulent* one. A wrong label is recoverable; an invented history that
    # every downstream reader now trusts is not.
    #
    # So the verb refuses, explains, and requires an explicit operator decision.
    # It never advances the store here — not even under the operator flag (see
    # `apply_repair`), because the refusal to invent history is absolute and the
    # flag only authorises correcting the label DOWNWARD to the honest floor.
    if store == "INIT" and label == "COMPLETE":
        return Repair(
            issue_number, label, store, merged, CLASS_LEGACY_UNDRIVEN,
            refused=True,
            reason=(
                "store=INIT with label=COMPLETE: this record was never driven "
                "through the phase machine, so there is no history to restore — "
                "only one to invent. Replaying INIT->COMPLETE would fabricate an "
                "audit trail that never happened, which is worse than the drift "
                "it replaces. REFUSED; requires an explicit operator decision "
                "(--allow-legacy-undriven), and even then the label is only "
                "re-projected down to the honest floor, never advanced."
            ),
        )

    # ---- Classes 2 and 3: the label claims COMPLETE it never earned ------
    if label == "COMPLETE" and _spine_index(store) is not None:
        steps = missing_steps(store, "COMPLETE")
        if merged and steps:
            # The work provably landed — a merged PR closed this issue. The
            # label is right about the destination and wrong about the journey,
            # so let the store EARN the remaining steps: replay them one legal
            # single step at a time through IssueManager.update, each validated
            # and recorded by the phase machine. It lands at COMPLETE having
            # earned it.
            return Repair(
                issue_number, label, store, merged, CLASS_UNEARNED_WORK_LANDED,
                transitions=steps,
                reason=(
                    f"label=COMPLETE, store={store}, and a merged PR closed this "
                    f"issue — the work landed. Replay the missing legal steps "
                    f"({' -> '.join(steps)}) through IssueManager.update so each "
                    f"is validated by the phase machine and the store earns "
                    f"COMPLETE instead of being handed it."
                ),
            )
        # No merge evidence. The label is simply false. Re-project from the
        # store and do NOT advance it — there is nothing proving the work landed.
        return Repair(
            issue_number, label, store, merged, CLASS_UNEARNED_NO_EVIDENCE,
            reproject_to=store,
            reason=(
                f"label=COMPLETE, store={store}, and no merged PR closes this "
                f"issue. Nothing evidences the work landing, so the label is "
                f"simply false: re-project it to {store}. The store is NOT "
                f"advanced."
            ),
        )

    # ---- Class 1: ordinary projection lag --------------------------------
    # The store already holds the truth (typically ahead of the label). Re-derive
    # the projection. No store write.
    return Repair(
        issue_number, label, store, merged, CLASS_PROJECTION_LAG,
        reproject_to=store,
        reason=(
            f"label={label or 'none'} disagrees with store={store} and makes no "
            f"COMPLETE claim — ordinary projection lag. The store already holds "
            f"the truth; re-derive the label from it."
        ),
    )


# ---------------------------------------------------------------------------
# Evidence
# ---------------------------------------------------------------------------

def fetch_merged_closers(limit: int = 1000) -> Set[int]:
    """Issue numbers closed by a **merged** PR — the only "work landed" evidence.

    One ``gh pr list`` call rather than a per-issue query: classifying 236
    records must not cost 236 round trips. Returns an empty set (after printing)
    when ``gh`` fails, which downgrades every class-2 candidate to class 3 —
    fail-SAFE, because class 3 never advances the store.
    """
    try:
        result = subprocess.run(
            [
                "gh", "pr", "list",
                "--state", "merged",
                "--limit", str(limit),
                "--json", "number,closingIssuesReferences",
            ],
            capture_output=True, text=True, timeout=120,
        )
    except (OSError, subprocess.SubprocessError) as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-11-30
        print(f"  Warning: merge evidence unavailable ({exc}); "
              f"treating every record as class 3 (no store advance).")
        return set()

    if result.returncode != 0:
        print(f"  Warning: gh pr list failed: {result.stderr.strip()}; "
              f"treating every record as class 3 (no store advance).")
        return set()

    try:
        prs = json.loads(result.stdout) or []
    except (json.JSONDecodeError, ValueError) as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-11-30
        print(f"  Warning: could not parse gh output: {exc}; "
              f"treating every record as class 3 (no store advance).")
        return set()

    closed: Set[int] = set()
    for pr in prs:
        for ref in pr.get("closingIssuesReferences") or []:
            number = ref.get("number")
            if number is not None:
                closed.add(int(number))
    return closed


def fetch_labelled_issues(limit: int = 1000) -> Optional[List[dict]]:
    """Every ``atdd-issue`` (open AND closed) with its labels.

    Closed issues are the whole point — the ``label=COMPLETE`` signature only
    exists on records a merge closed. Restricting to open issues would never
    reach 217 of the 236.
    """
    result = subprocess.run(
        [
            "gh", "issue", "list",
            "--label", "atdd-issue",
            "--state", "all",
            "--limit", str(limit),
            "--json", "number,title,state,labels",
        ],
        capture_output=True, text=True, timeout=120,
    )
    if result.returncode != 0:
        print(f"Error: gh issue list failed: {result.stderr.strip()}")
        return None
    try:
        return json.loads(result.stdout) or []
    except (json.JSONDecodeError, ValueError) as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-11-30
        print(f"Error: could not parse gh output: {exc}")
        return None


def phase_from_labels(labels: Sequence) -> Optional[str]:
    """The ``atdd:<PHASE>`` label's phase, or None when the issue carries none."""
    for entry in labels or []:
        name = entry.get("name") if isinstance(entry, dict) else entry
        if isinstance(name, str) and name.startswith("atdd:") and name != "atdd-issue":
            return name.split(":", 1)[1].upper()
    return None


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

@dataclass
class ReconcileReport:
    repairs: List[Repair] = field(default_factory=list)

    def by_class(self) -> Dict[int, List[Repair]]:
        buckets: Dict[int, List[Repair]] = {}
        for repair in self.repairs:
            buckets.setdefault(repair.repair_class, []).append(repair)
        return buckets

    def render(self, dry_run: bool = True) -> str:
        """The classification table the operator approves before anything writes."""
        lines: List[str] = []
        header = "reconcile-state — what WOULD change" if dry_run else "reconcile-state — applied"
        lines.append(header)
        lines.append("=" * len(header))
        lines.append("")

        buckets = self.by_class()
        drifted = [r for r in self.repairs if r.repair_class != CLASS_IN_SYNC]
        lines.append(
            f"{len(self.repairs)} record(s) examined — "
            f"{len(self.repairs) - len(drifted)} in sync, {len(drifted)} drifted"
        )
        lines.append("")

        for cls in sorted(buckets):
            group = buckets[cls]
            marker = "REFUSED" if any(r.refused for r in group) else (
                "no-op" if all(r.is_noop for r in group) else "repairable"
            )
            lines.append(f"class {cls} — {CLASS_NAMES[cls]} [{marker}]: {len(group)}")
            for repair in sorted(group, key=lambda r: r.issue_number):
                if repair.repair_class == CLASS_IN_SYNC:
                    continue
                plan = (
                    " -> ".join(repair.transitions) if repair.transitions
                    else (f"re-project label := {repair.reproject_to}"
                          if repair.reproject_to else "none")
                )
                lines.append(
                    f"    #{repair.issue_number:<6} "
                    f"label={repair.label_phase or 'none':<9} "
                    f"store={repair.store_phase or 'none':<9} "
                    f"merged={'yes' if repair.merged else 'no':<3} "
                    f"action: {plan}"
                )
            lines.append("")

        if dry_run:
            lines.append(
                "DRY RUN — nothing was written. Re-run with `--apply` on a single "
                "issue number to repair it."
            )
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Apply
# ---------------------------------------------------------------------------

def apply_repair(
    repair: Repair,
    *,
    target_dir: Optional[Path] = None,
    allow_legacy_undriven: bool = False,
    transition: Optional[Callable[..., int]] = None,
    reproject: Optional[Callable[[int], Optional[str]]] = None,
) -> int:
    """Execute one repair. Returns 0 on success, non-zero on refusal/failure.

    EVERY write goes through the authoritative writers:

    - a replay drives ``issue_transition.apply_transition`` one legal phase at a
      time, so the phase machine, the train gate and the COMPLETE gates all run;
    - a re-projection drives ``IssueManager.reproject_phase_label``, the only
      allowlisted ``atdd:*`` label writer (#1452).

    ``objects.state`` is NEVER written directly from here. ``transition`` and
    ``reproject`` are injectable purely so the repair classes can be driven in a
    hermetic test without touching live GitHub.
    """
    if repair.repair_class == CLASS_UNKNOWN_TO_STORE:
        print(f"#{repair.issue_number}: skipped — {repair.reason}")
        return 1

    if repair.refused and not allow_legacy_undriven:
        print(f"#{repair.issue_number}: REFUSED — {repair.reason}")
        return 1

    if repair.refused and allow_legacy_undriven:
        # The operator decision authorises correcting the label DOWN to the
        # honest floor. It does NOT authorise a replay — no flag does. Fabricated
        # history is unreachable by construction, not merely discouraged.
        print(
            f"#{repair.issue_number}: operator-authorised (--allow-legacy-undriven) "
            f"— re-projecting the label down to the honest floor "
            f"{repair.store_phase}. The store is NOT advanced and no history is "
            f"synthesised."
        )
        repair = Repair(
            repair.issue_number, repair.label_phase, repair.store_phase,
            repair.merged, repair.repair_class, repair.reason,
            reproject_to=repair.store_phase, refused=False,
        )

    if repair.is_noop:
        print(f"#{repair.issue_number}: no-op — {repair.reason}")
        return 0

    if repair.reproject_to:
        if reproject is None:
            from atdd.coach.commands.issue import IssueManager

            reproject = IssueManager(target_dir).reproject_phase_label
        projected = reproject(repair.issue_number)
        if projected is None:
            print(f"#{repair.issue_number}: re-projection failed — store unreadable.")
            return 1
        print(f"#{repair.issue_number}: label re-projected from the store := {projected}")
        return 0

    if transition is None:
        from atdd.coach.commands.issue_transition import apply_transition

        transition = apply_transition
    for phase in repair.transitions:
        rc = transition(repair.issue_number, phase, target_dir=target_dir)
        if rc != 0:
            print(
                f"#{repair.issue_number}: replay stopped at {phase} (exit {rc}). "
                f"The phase machine refused this step — the store keeps whatever "
                f"it legally earned so far, and nothing was forced."
            )
            return rc
        print(f"#{repair.issue_number}: replayed -> {phase}")
    return 0


def build_report(
    issue_numbers: Optional[Sequence[int]] = None,
    *,
    target_dir: Optional[Path] = None,
) -> Optional[ReconcileReport]:
    """Classify ``issue_numbers`` (or every ``atdd-issue`` when None)."""
    from atdd.coach.commands.auto_phase import read_store_phase

    issues = fetch_labelled_issues()
    if issues is None:
        return None
    if issue_numbers is not None:
        wanted = set(issue_numbers)
        issues = [i for i in issues if i.get("number") in wanted]

    merged_closers = fetch_merged_closers()

    report = ReconcileReport()
    for issue in issues:
        number = issue.get("number")
        if number is None:
            continue
        report.repairs.append(
            classify(
                int(number),
                phase_from_labels(issue.get("labels") or []),
                read_store_phase(int(number), target_dir),
                int(number) in merged_closers,
            )
        )
    return report
