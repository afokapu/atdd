# Component: component:atdd-plan-core:session-machine:PlanSession:backend:domain
"""atdd plan — the gated decomposition session state machine (#1139).

The harness around the conversation: the LLM/agent runs the dialogue and calls
these APIs; this module holds the **durable gated session state** (on disk,
surviving long conversations / compaction) and enforces the stage gates.

Lifecycle: Intent -> Attach -> Compose -> Ratify -> (authored). The stages name
what the OPERATOR is deciding, not what the tool is doing: Intent declares the
job to be done and its boundaries, Attach connects that intent to existing
repository context, Compose arranges the proposed train, Ratify approves,
rejects or redirects the composition and locks it, and Author materialises it
as schema-valid artifacts.

Stages are gates, not scripts: free dialogue within a stage; a stage advances
only when its exit condition holds; backtracking is allowed. keep/pivot/kill
rides the #1096a `elicit` contract (a consumer, never AskUserQuestion
directly). The Ratify gate is the conversational->deterministic boundary:
nothing is authored until the operator ratifies the locked decomposition.

That boundary keeps its rule name, `planner.plan.confirm-before-author`, and
this module keeps its `confirm()` method and its `confirm_*` collaborators. The
rule name and the stage name are separate things: the STAGE is now Ratify, the
RULE is still confirm-before-author (#1688). Both are true at once.

Stdlib + the neutral elicit contract only.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path

from atdd.runtime.elicit import (
    AtddRole, ElicitKind, ElicitRequest, ElicitResponse, ElicitRole,
    ElicitStatus, Participant,
)


class Step(str, Enum):
    INTENT = "intent"      # declare the JTBD main job and its boundaries
    ATTACH = "attach"      # connect the intent to existing repository context
    COMPOSE = "compose"    # arrange the proposed decomposition
    RATIFY = "ratify"      # operator keep/pivot/kill -> lock
    AUTHORED = "authored"  # post-ratify: atdd author has written the locked units


_ORDER = [Step.INTENT, Step.ATTACH, Step.COMPOSE, Step.RATIFY, Step.AUTHORED]

# Stage values written before the #1688 rename, mapped to what they now mean.
# `.atdd/runtime/` is gitignored, so sessions are machine-local and disposable —
# but they are real, and `load()` is `cls(**data)` with no validation, so a stale
# value would survive the load and detonate on the NEXT `Step(self.step)` as a
# bare ValueError. ValueError is not SessionGateError, so it escapes the CLI's
# handler and reaches the operator as a traceback instead of a refusal.
_LEGACY_STEP_VALUES = {
    "define": Step.INTENT.value,
    "locate": Step.ATTACH.value,
    "prepare": Step.COMPOSE.value,
    "confirm": Step.RATIFY.value,
}


class Verdict(str, Enum):
    PENDING = "pending"
    KEEP = "keep"
    PIVOT = "pivot"
    KILL = "kill"


class SessionGateError(RuntimeError):
    """Raised when a stage transition's exit condition is not met, or when
    authoring is attempted before the Ratify lock (confirm-before-author)."""


@dataclass
class Unit:
    """A decomposition candidate the operator decides on (keep/pivot/kill)."""
    kind: str                      # main-job | heuristic | analog | wagon | feature | wmbt | train | interlocking | contract | acceptance
    ref: str                       # slug / urn / label
    verdict: str = Verdict.PENDING.value
    modification: str | None = None  # named modification when pivoted
    spec: dict = field(default_factory=dict)  # the atdd author spec (filled in Compose)


@dataclass
class PlanSession:
    session_id: str
    step: str = Step.INTENT.value
    main_job: str | None = None
    sources: list = field(default_factory=list)   # captured source descriptors
    units: list = field(default_factory=list)     # list[Unit] (as dicts when persisted)
    locked: bool = False
    issue_ref: str | None = None  # local issue identity (manifest slug) this plan binds to;
    # the SoT is the local manifest/State Store record (#945/#1168), NOT a GitHub number — the
    # GitHub issue number is a downstream projection the github extension syncs after install.

    # ---- persistence -------------------------------------------------------
    @staticmethod
    def _home(root: Path | str, session_id: str) -> Path:
        return Path(root) / ".atdd" / "runtime" / "plan-sessions" / session_id / "session.json"

    def save(self, root: Path | str = ".") -> Path:
        path = self._home(root, self.session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = asdict(self)
        data["units"] = [u if isinstance(u, dict) else asdict(u) for u in self.units]
        path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
        return path

    @classmethod
    def load(cls, session_id: str, root: Path | str = ".") -> "PlanSession":
        path = cls._home(root, session_id)
        if not path.exists():
            raise SessionGateError(f"no plan session {session_id!r} at {path}")
        data = json.loads(path.read_text(encoding="utf-8"))
        step = data.get("step")
        if isinstance(step, str) and step in _LEGACY_STEP_VALUES:
            data["step"] = _LEGACY_STEP_VALUES[step]  # pre-#1688 session
        return cls(**data)

    # ---- the Ratify lock ---------------------------------------------------
    def assert_mutable(self, what: str) -> None:
        """Refuse a mutation while the decomposition is locked (#1505).

        ``locked`` is an invariant, not a marker: it is the operator's assertion
        that *this exact unit set* may be authored, and ``confirm()`` is where the
        interlocking (#1249), verb-object (#1276) and artifact-naming (#1329)
        validations run. A unit slipped in after the lock would be seen by none of
        them, so what you confirmed is what gets authored — ``reopen()`` is the one
        sanctioned way to withdraw the assertion and edit again.
        """
        if self.locked:
            raise SessionGateError(
                f"the decomposition is locked — cannot {what}. What you ratified is "
                f"what gets authored: units added after Ratify would never be seen by "
                f"the interlocking, verb-object and artifact-naming validations that "
                f"the Ratify gate runs. To edit, withdraw the ratification first: "
                f"`atdd plan reopen --id {self.session_id}` (returns the session to "
                f"Compose and keeps your verdicts), then re-run `atdd plan ratify`.")

    def reopen(self) -> None:
        """Withdraw the operator's ratification and return to Compose (#1505).

        The sanctioned escape from a locked session — sanctioned because
        ``planner.plan.session-lifecycle`` already allows a pivot to reopen an
        earlier stage. Verdicts are PRESERVED: the Ratify gate re-runs every
        validation against the *current* unit set regardless of verdict age, so
        keeping them bypasses nothing, while resetting them would punish a large
        decomposition for a one-unit edit and push operators back to hand-editing
        session.json.

        Refused once ``step == AUTHORED``: the artifacts are already on disk, and
        reopening would leave them orphaned with no rollback to offer.
        """
        if Step(self.step) is Step.AUTHORED:
            raise SessionGateError(
                "cannot reopen a session that has already authored its units — the "
                "artifacts are on disk and reopening would orphan them. Author the "
                "change as a new plan session against the same issue instead.")
        self.locked = False
        self.step = Step.COMPOSE.value

    # ---- units -------------------------------------------------------------
    def add_unit(self, unit: Unit) -> None:
        """Add a candidate unit, or update the one already carrying this ``ref``.

        ``ref`` identifies a unit within a session — ``_unit()`` has always
        resolved by ``ref`` alone, so two units sharing one ``ref`` made the
        session ambiguous: ``decide()`` reached only the first while ``author()``
        wrote both. Re-stating a unit is the normal Compose loop (draft, look,
        re-draft), so it upserts rather than appending a duplicate.

        Changing a decided unit's ``spec`` resets its verdict to PENDING: the
        thing the operator decided on is no longer the thing in the session, and
        ``confirm()`` requires a terminal verdict, so the change must be
        re-decided. Re-stating an identical spec keeps the verdict.

        Re-using a ``ref`` under a different ``kind`` is refused — that is an
        operator mistake, not an update, and silently changing a unit's kind
        would send it to a different ``atdd author`` writer.

        Refused outright while the session is locked (#1505). The upsert path
        makes this stricter than it looks: re-stating an existing unit with a
        changed spec *rewrites* that unit and resets its verdict, so an upsert on
        a confirmed session would mutate a decomposition the operator had already
        signed off — the same bypass as appending a new unit, wearing the shape of
        an edit. The guard runs before the ref scan so both paths are covered.
        """
        self.assert_mutable(f"add the {unit.kind} unit {unit.ref!r}")
        incoming = asdict(unit)
        for i, existing in enumerate(self.units):
            if existing["ref"] != incoming["ref"]:
                continue
            if existing["kind"] != incoming["kind"]:
                raise SessionGateError(
                    f"unit {incoming['ref']!r} already exists as kind "
                    f"{existing['kind']!r}; refusing to redefine it as "
                    f"{incoming['kind']!r} — use a distinct ref")
            if existing["spec"] != incoming["spec"]:
                self.units[i] = incoming  # spec changed -> verdict resets to PENDING
            # identical spec: a no-op, so a replay never discards a verdict or
            # the modification a pivot recorded.
            return
        self.units.append(incoming)

    def _unit(self, ref: str) -> dict:
        for u in self.units:
            if u["ref"] == ref:
                return u
        raise SessionGateError(f"no unit {ref!r} in session {self.session_id}")

    def kept_units(self) -> list:
        return [u for u in self.units if u["verdict"] == Verdict.KEEP.value]

    # ---- keep/pivot/kill via the #1096a elicit contract --------------------
    def decide(self, ref: str, elicit, *, session_ref: str | None = None) -> ElicitResponse:
        """Ask the operator keep/pivot/kill for one unit, via the elicit channel
        (a consumer of #1096a — never AskUserQuestion directly). Records the verdict."""
        unit = self._unit(ref)
        self.assert_mutable(f"re-decide the {unit['kind']} {ref!r}")
        req = ElicitRequest(
            elicit_id=f"{self.session_id}:{ref}",
            origin=Participant(ElicitRole.CONDUCTOR, session_ref or f"atdd-plan-session:{self.session_id}", AtddRole.PLANNER),
            kind=ElicitKind.CONFIRMATION,
            prompt=f"Keep, pivot, or kill the {unit['kind']} '{ref}'?",
            questions=[{"id": "verdict", "prompt": f"{unit['kind']} {ref}?", "multiSelect": False,
                        "options": [{"label": "keep"}, {"label": "pivot"}, {"label": "kill"}]}],
        )
        resp = elicit.elicit(req)
        if resp.status is ElicitStatus.RESOLVED and resp.selections:
            unit["verdict"] = resp.selections[0]
            if resp.selections[0] == Verdict.PIVOT.value:
                unit["modification"] = resp.freeform
        return resp

    # ---- gated transitions -------------------------------------------------
    def _gate_ok(self, target: Step) -> tuple[bool, str]:
        """Whether ``target`` may be entered, and why not when it may not.

        Note the direction of the messages: each names the stage being LEFT, not
        the one being entered, because that is the stage whose exit condition the
        operator has to satisfy. So the branch for ``ATTACH`` explains why
        ``Intent`` will not release the session. Renaming a message to match its
        own branch target would silently shift all four by one stage.
        """
        if target is Step.ATTACH:
            ok = any(u["kind"] == "main-job" and u["verdict"] == Verdict.KEEP.value for u in self.units) or bool(self.main_job)
            return ok, "Intent requires a kept JTBD main job"
        if target is Step.COMPOSE:
            return bool(self.sources), "Attach requires captured sources / plan state"
        if target is Step.RATIFY:
            cand = [u for u in self.units if u["kind"] not in ("main-job", "heuristic", "analog")]
            return bool(cand), "Compose requires at least one candidate decomposition unit"
        if target is Step.AUTHORED:
            return self.locked, "Ratify requires the decomposition to be locked by the operator"
        return False, f"unknown target {target}"

    def advance(self, target: Step) -> None:
        """Advance to `target` if its exit condition holds. Backtracking (to an
        earlier stage) is always allowed and does not re-check gates.

        Backtracking CLEARS the lock (#1505). The flag asserts 'this exact unit set
        may be authored'; stepping back to edit withdraws that assertion, so leaving
        it set would let `_gate_ok(AUTHORED)` wave the session through on a stale
        ratification that never saw the current units. A no-op (`target is cur`) is
        not a backtrack and leaves the lock alone.
        """
        cur = Step(self.step)
        if _ORDER.index(target) < _ORDER.index(cur):
            self.step = target.value  # backtrack
            self.locked = False
            return
        if target is cur:
            return  # no-op: not an edit, so the operator's confirmation stands
        if _ORDER.index(target) != _ORDER.index(cur) + 1:
            raise SessionGateError(f"cannot skip from {cur.value} to {target.value}")
        ok, why = self._gate_ok(target)
        if not ok:
            raise SessionGateError(why)
        self.step = target.value

    def confirm(self, root: Path | str = ".") -> None:
        """The Ratify gate: every unit must reach a TERMINAL verdict (keep or
        kill) before locking. PENDING and PIVOT are non-terminal — a pivot names
        a modification that must be re-drafted and re-decided (decide() again to
        keep/kill) before ratifying. This is the conversational->deterministic
        boundary.

        The method keeps the name ``confirm()`` deliberately: the rule it enforces
        is ``planner.plan.confirm-before-author`` and its collaborators are the
        ``confirm_*`` modules, all of which are bound identities that this rename
        does not touch (#1688). The STAGE is Ratify; the RULE is
        confirm-before-author.

        Before locking, kept train units' interlocking sanity is validated via
        the #1248 Python API (``planner.plan.confirm-requires-interlocking-sanity``,
        #1249). The gate fails closed and is atomic: every failure path raises
        ``SessionGateError`` and leaves ``self.locked is False``."""
        if Step(self.step) is not Step.RATIFY:
            raise SessionGateError("ratify is only valid in the Ratify stage")
        unresolved = [u["ref"] for u in self.units
                      if u["verdict"] in (Verdict.PENDING.value, Verdict.PIVOT.value)]
        if unresolved:
            raise SessionGateError(
                f"unresolved units — keep or kill required (pivots must be re-resolved): {unresolved}")
        if self.issue_ref is None:
            raise SessionGateError(
                "confirm-binds-an-issue: the decomposition must be bound to a local ATDD issue "
                "record (a target issue, or one minted from the main job) before lock — every "
                "authored plan modification is tracked by an issue + branch + worktree (the "
                "universal rule). The binding is the local manifest/State Store slug, NOT a GitHub "
                "number (GitHub is a downstream extension). "
                "Set it via `atdd plan session bind-issue --id <sess> --issue <slug>`.")
        # Interlocking sanity for kept train units (#1249). Runs BEFORE the lock,
        # so a failure raises and leaves the session unlocked (atomicity). A kept
        # train with no interlocking reference is a direct train and is allowed.
        from atdd.planner.commands.confirm_interlocking import (
            assert_kept_train_interlocking_sanity,
        )
        assert_kept_train_interlocking_sanity(self, root)
        # Foundational verb-object naming for kept wagon/feature units (#1276).
        # Runs BEFORE the lock so a non-verb-object name raises and leaves the
        # session unlocked (atomicity, same contract as interlocking sanity).
        from atdd.planner.commands.confirm_naming import (
            assert_kept_wagon_feature_naming,
        )
        assert_kept_wagon_feature_naming(self, root)
        # Foundational artifact/contract naming for kept wagon produce[] (#1329).
        # Same atomic, before-lock contract: a non-theme-first artifact identity
        # or a contract path that does not mirror it raises and leaves the
        # session unlocked.
        from atdd.planner.commands.confirm_artifact_naming import (
            assert_kept_artifact_naming,
        )
        assert_kept_artifact_naming(self, root)
        self.locked = True

    def author(self, author_fn) -> list:
        """Post-ratify: deterministically author each KEPT unit via `author_fn`
        (the #1144 atdd-author writers). Refuses if not locked
        (planner.plan.confirm-before-author — the rule name is unchanged)."""
        if not self.locked:
            raise SessionGateError(
                "confirm-before-author: nothing may be authored before the operator ratifies")
        results = [author_fn(u["kind"], u["spec"]) for u in self.kept_units()]
        self.advance(Step.AUTHORED)
        return results


def build_author_fn(root: Path | str = "."):
    """The on-Ratify deterministic dispatch: map a locked unit's kind to its
    #1144 `atdd author` writer. atdd plan invokes this — the system, not the agent."""
    from atdd.planner.commands.author import (
        create_acceptance, create_contract, create_feature, create_interlocking,
        create_train, create_wagon, create_wmbt,
    )

    def _author(kind: str, spec: dict):
        if kind == "wagon":
            return create_wagon(spec, root=root)
        if kind == "feature":
            return create_feature(spec, root=root)
        if kind == "wmbt":
            return create_wmbt(spec, root=root)
        if kind == "train":
            return create_train(spec, root=root)
        if kind == "interlocking":
            return create_interlocking(spec, root=root)
        if kind == "contract":
            return create_contract(spec, root=root)
        if kind == "acceptance":
            return create_acceptance(spec["wmbt_urn"], spec["block"], root=root)
        raise SessionGateError(f"no atdd author writer for plan kind {kind!r}")

    return _author
