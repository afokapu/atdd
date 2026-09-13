"""LabEvidenceGateCheck (#1950) — evidence-gated ``INIT->PLANNED``.

The lifecycle gates DELIVERY thoroughly — RED before GREEN, smoke evidence before
REFACTOR, an operator at both ends — and gates PREMISE not at all. INIT asks for
scope, architecture and decisions, every one of which can be written confidently and
be wrong, and nothing between INIT and code asks whether any of it was checked
against the system. This check asks, of the one artifact that can answer: the
issue's own ``## Lab`` section.

TWO CLAUSES, AND NO MORE. A subsection is unfilled when its content is *empty*, or
when it *opens with* an unfilled marker. That is the whole judgement. Two things
that look like obvious additions are deliberately absent:

DELIBERATELY NOT ``issue_template.check_placeholders``. That check fires only when a
placeholder is the WHOLE LINE — correctly, since #1904 measured the substring form
producing four hits over 120 issues and zero real ones ("JTBD" contains "TBD"). But
every hand-written lab in this repo writes the marker followed by explanatory prose
on one line, so the marker is never the whole line: three live bodies that literally
say "To fill" all report ``compliant=True, placeholder_hits=[]``. Anchoring at the
START of a subsection's content sees them; anchoring at a line boundary cannot.

DELIBERATELY NO LENGTH FLOOR. A 40-character minimum was tried in the lab and
refused four of six legitimate terse answers — ``Nothing.``, the correct result for
a confirmed hypothesis, and a one-row result table among them. That is #1903's
lesson exactly: a check that punishes authors for stating the truth concisely. The
empty clause and the marker clause cover every state the length floor caught, so it
bought nothing and cost the honest terse answer.

WHAT IT DOES NOT JUDGE. Whether the lab was GOOD. An author who deletes the markers
and writes evasive-but-real prose passes, and no mechanical check closes that — it
is a reviewer's job. This gate asks only whether an experiment was run and its
result recorded.

SHIPS INERT. ``INIT->PLANNED`` is absent from ``DEFAULT_GATED_TRANSITIONS``, and
``evaluate_transition_gate`` consults ``is_transition_gated`` BEFORE the registry,
so registering this check enables nothing on its own. Measured: with the edge gated
repo-wide it refuses 162 of 163 open-at-INIT issues, and unlike
``SmokeExecutionGateCheck`` there is no per-issue opt-in to soften it — every issue
has a premise, so nothing is ever "not applicable". Enabling it before the backlog
is triaged would make ``--force`` the routine exit, which is the rubber-stamp
failure this repo's own config comment warns about for ``SMOKE->REFACTOR``.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import List, Optional

from atdd.coach.gate.decision import GateCheckResult, GateContext

logger = logging.getLogger(__name__)

GATE_ID = "lab-evidence"
RULE_ID = "coach.lifecycle.no-init-to-planned-without-lab"

#: ``external_refs`` coordinates of the GitHub issue projection (#1183) — the same
#: pair :class:`~atdd.state.work_item_reader.WorkItemReader` resolves by.
_GITHUB_PROVIDER = "github"
_ISSUE_REF_KIND = "issue"

#: The four subsections, in the order an operator fills them.
SUBSECTIONS: tuple[str, ...] = (
    "Hypothesis",
    "Setup",
    "Measured result",
    "What it changed about the plan",
)

#: Content that OPENS with one of these is still unfilled, whatever follows it.
#:
#: Anchored at ``^`` against the subsection's content — not against a line — which
#: is the whole difference between this and ``check_placeholders``. ``nothing yet``
#: carries its ``yet`` on purpose: bare ``Nothing.`` is the correct answer for a
#: hypothesis that held, and must pass.
_UNFILLED = re.compile(
    r"^\s*[_*`]*\s*(to fill\b|tbd\b|n/?a\b|todo\b|not measured|nothing yet)",
    re.IGNORECASE,
)

#: `## Lab` and everything up to the next H2. ``^##\s`` cannot match an H3: after two
#: hashes the third ``#`` fails ``\s``.
_LAB_SECTION = re.compile(r"^##\s+Lab\s*$(.*?)(?=^##\s|\Z)", re.MULTILINE | re.DOTALL)
_SUBSECTION = re.compile(r"^###\s+(.+?)\s*$(.*?)(?=^###\s|\Z)", re.MULTILINE | re.DOTALL)


def _scaffold() -> dict:
    """The generator's own scaffold strings, read fresh on every call.

    Read rather than cached so a reworded prompt is followed immediately; a module-
    level copy would be a second description of the same fact, which is the defect
    this whole mechanism exists to avoid. Returns ``{}`` when the planner package is
    unavailable — the marker clause still applies, so the gate degrades to weaker
    rather than to blind.
    """
    try:
        from atdd.planner.commands.author_issue import LAB_SCAFFOLD

        return dict(LAB_SCAFFOLD)
    except Exception:  # noqa: BLE001 - a missing generator must not crash the gate
        logger.debug("lab-evidence gate: LAB_SCAFFOLD unavailable; marker clause only")
        return {}


def lab_violations(body: str) -> List[str]:
    """Every reason ``## Lab`` fails to constitute evidence; empty means satisfied.

    Pure: no store, no network, no filesystem. The impure half — resolving which
    body belongs to an issue number — lives in :class:`LabEvidenceGateCheck`, so the
    judgement itself is testable against a string.
    """
    match = _LAB_SECTION.search(body or "")
    if match is None:
        return ["`## Lab` is absent — INIT's exit asks for evidence the premise was tested"]

    found = {name: text for name, text in _SUBSECTION.findall(match.group(1))}
    scaffold = _scaffold()
    violations: List[str] = []

    for name in SUBSECTIONS:
        if name not in found:
            violations.append(f"`### {name}` is absent")
            continue
        content = found[name].strip()
        prompt = scaffold.get(name)
        if not content:
            violations.append(f"`### {name}` is empty")
        elif prompt and content.startswith(prompt):
            violations.append(f"`### {name}` still carries its scaffold prompt")
        elif _UNFILLED.search(content):
            violations.append(
                f"`### {name}` still opens with an unfilled marker: "
                f"{content.splitlines()[0][:60]!r}"
            )
    return violations


def resolve_issue_body(store, issue_number: int) -> Optional[str]:
    """The stored body for *issue_number*, or ``None`` when it cannot be resolved.

    ``None`` is never "no obligation" — the caller fails closed on it. A gate that
    advances on an unmade observation is the defect this check exists inside.
    """
    ref = store.external_refs.resolve(_GITHUB_PROVIDER, _ISSUE_REF_KIND, str(issue_number))
    if ref is None:
        return None
    obj = store.objects.get(ref.object_uid)
    data = getattr(obj, "data", None)
    body = data.get("body") if isinstance(data, dict) else None
    return body if isinstance(body, str) else None


@dataclass(frozen=True)
class LabEvidenceGateCheck:
    """Passes iff the issue's ``## Lab`` records an experiment that was run."""

    gate_id: str = GATE_ID
    rule_id: str = RULE_ID

    def run(self, ctx: GateContext) -> GateCheckResult:
        transition = f"{ctx.from_phase.upper()}->{ctx.to_phase.upper()}"
        produce = (
            "fill `## Lab` — state the premise, how it was tested against the real "
            "system, what was measured, and what that changed about the plan. A "
            "DISPROVED hypothesis satisfies this gate; an unrun one does not"
        )

        body = self._body(ctx)
        if body is None:
            return GateCheckResult(
                self.gate_id, self.rule_id, False,
                f"{transition} refused for #{ctx.issue_number}: its body could not be "
                f"resolved from the State Store, so no lab evidence can be read "
                f"(fail-closed); {produce}",
            )

        violations = lab_violations(body)
        if violations:
            logger.warning(
                "lab-evidence gate refused a transition",
                extra={"gate_id": self.gate_id, "rule_id": self.rule_id,
                       "issue": ctx.issue_number, "violations": len(violations)},
            )
            return GateCheckResult(
                self.gate_id, self.rule_id, False,
                f"{transition} refused for #{ctx.issue_number}: "
                + "; ".join(violations)
                + f". {produce}",
            )

        return GateCheckResult(
            self.gate_id, self.rule_id, True,
            f"{transition} carries lab evidence for #{ctx.issue_number}: all four "
            f"`## Lab` subsections are filled",
        )

    def _body(self, ctx: GateContext) -> Optional[str]:
        """Read the issue body from the store, or ``None`` on any failure."""
        try:
            from atdd.state.smoke_evidence import open_state_store

            with open_state_store(control_root=ctx.worktree) as store:
                return resolve_issue_body(store, ctx.issue_number)
        except Exception as exc:  # noqa: BLE001 - an unreachable store fails closed
            logger.debug(
                "lab-evidence gate: cannot read the issue body",
                extra={"issue": getattr(ctx, "issue_number", None), "error": str(exc)},
            )
            return None
