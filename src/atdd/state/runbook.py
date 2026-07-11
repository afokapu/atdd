"""The migration runbook, and the check that it stays true (#1400 CORE-035, D001).

A runbook is the one migration artifact that rots silently. The code moves, the steps change, and
the document keeps confidently describing a cutover nobody performs any more — right up until the
night someone follows it. So the runbook is *checked*, against the steps the code actually ships:

**Every migration step has a section** (D001-UNIT-001), and each section states its ``Command``,
its ``Precondition``, and the ``Invariant`` it preserves. Add a step to :data:`MIGRATION_STEPS`
without documenting it and the check goes red; document a step that no longer exists and it goes
red the other way.

**Every section cites a real, numbered invariant** (D001-UNIT-002). Not a paraphrase — one of the
``I1``–``I8`` in spec §2.2, parsed *out of the spec* rather than hardcoded here, so a section that
cites ``I9`` fails because there is no I9, and not because this module happened to know that.

The reason the citation is mandatory: a runbook step that cannot name what it preserves is a step
whose author did not know. "Run the migration tool" is an instruction. "Run the migration tool;
it preserves I1, so a second run reproduces the first byte for byte" is an instruction the reader
can *verify they followed correctly* — which is the only kind worth writing down for a one-way door.

Dependency discipline: stdlib only.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

_log = logging.getLogger(__name__)

#: The authored runbook, relative to the repo root.
RUNBOOK_RELATIVE = Path("docs") / "atdd-migration-runbook.md"

#: The architecture spec, whose §2.2 table is the *only* source of legal invariant ids.
SPEC_RELATIVE = Path("docs") / "atdd-state-projection-plan.md"

#: An invariant id as the spec's §2.2 table declares it: `| I1 | ... |`.
_SPEC_INVARIANT_RE = re.compile(r"^\|\s*(I\d+)\s*\|", re.MULTILINE)

#: An invariant id as a runbook section cites it.
_CITATION_RE = re.compile(r"\bI\d+\b")

#: A section heading: `## <slug> — <title>`. The slug is the step id.
_HEADING_RE = re.compile(r"^##+\s+(?P<slug>[a-z0-9][a-z0-9-]*)\b", re.MULTILINE)

#: The three things every step must state. A step missing one is a step someone will get wrong.
REQUIRED_KEYS: Tuple[str, ...] = ("Command", "Precondition", "Invariant")


@dataclass(frozen=True)
class MigrationStep:
    """One step of the cutover, as the code actually ships it."""

    slug: str
    summary: str


#: The migration this wagon ships, in the order it must be performed. The runbook documents
#: exactly these — no more (a documented step that does not exist misleads), and no fewer.
MIGRATION_STEPS: Tuple[MigrationStep, ...] = (
    MigrationStep("mint-uids",
                  "Backfill an immutable uid into every legacy manifest entry, and commit it."),
    MigrationStep("migrate-manifest",
                  "Convert the legacy manifest into the uid-keyed committed projection."),
    MigrationStep("shadow",
                  "Run the non-blocking shadow projection CI and watch the drift go to zero."),
    MigrationStep("hot-path",
                  "Prove no lifecycle decision, validator, or gate calls the GitHub API."),
    MigrationStep("decommission-manifest",
                  "Prove no core reader consults .atdd/manifest.yaml, and delete it."),
    MigrationStep("blocking-mode",
                  "Turn the projection canonicality gate from advisory to required."),
    MigrationStep("cutover",
                  "Evaluate the three M8 exit criteria; the cutover is done when all three pass."),
)


@dataclass(frozen=True)
class RunbookProblem:
    """One thing wrong with the runbook."""

    rule: str
    step: str
    detail: str

    def render(self) -> str:
        return f"[{self.rule}] {self.step}: {self.detail}"


RULE_MISSING_SECTION = "missing-section"
RULE_MISSING_KEY = "missing-key"
RULE_NO_INVARIANT = "no-invariant-cited"
RULE_UNKNOWN_INVARIANT = "unknown-invariant"
RULE_UNDOCUMENTED_SECTION = "undocumented-section"


@dataclass(frozen=True)
class RunbookReport:
    """The verdict over the authored runbook."""

    problems: List[RunbookProblem] = field(default_factory=list)
    sections: List[str] = field(default_factory=list)
    #: The invariant ids the spec declares — the closed set a citation may draw from.
    known_invariants: List[str] = field(default_factory=list)
    #: step slug → the invariants its section cites.
    citations: Dict[str, List[str]] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.problems

    def render(self) -> str:
        if self.ok:
            return (
                f"the migration runbook covers all {len(self.sections)} migration step(s); every "
                f"section states its command, precondition, and a numbered invariant drawn from "
                f"the {len(self.known_invariants)} the spec declares."
            )
        return "\n".join([
            f"the migration runbook has {len(self.problems)} problem(s):",
            *(f"  {problem.render()}" for problem in self.problems),
        ])


def spec_invariants(spec: Path) -> List[str]:
    """The invariant ids the architecture spec declares (``I1``…``I8``), parsed from §2.2.

    Parsed, not hardcoded: "no section cites an invariant that does not exist" is only a real
    check if *the spec* decides what exists. A copy of the list here would let the runbook and the
    architecture drift apart while this module cheerfully agreed with both.
    """
    spec = Path(spec)
    if not spec.is_file():
        raise FileNotFoundError(f"the architecture spec is missing: {spec}")
    return sorted(set(_SPEC_INVARIANT_RE.findall(spec.read_text(encoding="utf-8"))),
                  key=lambda name: int(name[1:]))


def _sections(text: str) -> Dict[str, str]:
    """Every ``## <slug>`` section, slug → its body."""
    matches = list(_HEADING_RE.finditer(text))
    found: Dict[str, str] = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        found[match.group("slug")] = text[match.end():end]
    return found


def check(
    root: Path,
    *,
    steps: Sequence[MigrationStep] = MIGRATION_STEPS,
    runbook: Optional[Path] = None,
    spec: Optional[Path] = None,
) -> RunbookReport:
    """Check the authored runbook against the steps the code ships (D001)."""
    root = Path(root)
    runbook_path = Path(runbook) if runbook is not None else root / RUNBOOK_RELATIVE
    spec_path = Path(spec) if spec is not None else root / SPEC_RELATIVE

    known = spec_invariants(spec_path)
    if not runbook_path.is_file():
        return RunbookReport(
            problems=[RunbookProblem(RULE_MISSING_SECTION, step.slug,
                                     f"no runbook at {runbook_path}") for step in steps],
            known_invariants=known,
        )

    sections = _sections(runbook_path.read_text(encoding="utf-8"))
    problems: List[RunbookProblem] = []
    citations: Dict[str, List[str]] = {}

    for step in steps:
        body = sections.get(step.slug)
        if body is None:
            problems.append(RunbookProblem(
                RULE_MISSING_SECTION, step.slug,
                f"the runbook has no `## {step.slug}` section, but the code ships the step "
                f"({step.summary})",
            ))
            continue

        for key in REQUIRED_KEYS:
            if not re.search(rf"^\s*[-*]?\s*\*\*{key}\*\*", body, re.MULTILINE):
                problems.append(RunbookProblem(
                    RULE_MISSING_KEY, step.slug, f"the section states no **{key}**",
                ))

        cited = sorted(set(_CITATION_RE.findall(body)), key=lambda name: int(name[1:]))
        citations[step.slug] = cited
        if not cited:
            problems.append(RunbookProblem(
                RULE_NO_INVARIANT, step.slug,
                "the section cites no numbered invariant — a step that cannot name what it "
                "preserves is a step whose author did not know",
            ))
        for name in cited:
            if name not in known:
                problems.append(RunbookProblem(
                    RULE_UNKNOWN_INVARIANT, step.slug,
                    f"cites {name}, which the spec does not declare (it declares {known})",
                ))

    documented = {step.slug for step in steps}
    for slug in sorted(set(sections) - documented):
        problems.append(RunbookProblem(
            RULE_UNDOCUMENTED_SECTION, slug,
            "the runbook documents a migration step the code does not ship",
        ))

    if problems:
        _log.warning("the migration runbook does not match the steps the code ships",
                     extra={"runbook": str(runbook_path),
                            "problems": [p.render() for p in problems]})
    return RunbookReport(
        problems=problems, sections=sorted(sections), known_invariants=known, citations=citations,
    )


__all__ = [
    "MIGRATION_STEPS", "MigrationStep", "REQUIRED_KEYS", "RULE_MISSING_KEY", "RULE_MISSING_SECTION",
    "RULE_NO_INVARIANT", "RULE_UNDOCUMENTED_SECTION", "RULE_UNKNOWN_INVARIANT", "RUNBOOK_RELATIVE",
    "RunbookProblem", "RunbookReport", "SPEC_RELATIVE", "check", "spec_invariants",
]
