# URN: component:govern-lifecycle:enforcement-substrate:artifact_claims:backend:domain
# Runtime: python
# Purpose: The one implementation of the issue `## Artifacts` policy, bound to the convention.

"""The `## Artifacts` claim, checked once (issue #1726).

Before this module the section was enforced by TWO independent code paths --
``IssueManager._verify_artifacts`` (the COMPLETE runtime gate) and the coach
validator ``test_issue_gate_completion.py`` (the CI gate) -- and declared by NO
convention rule. With nothing to bind to, each implementation invented its own
policy, and both invented the same escape::

    total = sum(len(v) for v in artifacts.values())
    if total == 0:
        continue                                   # the validator skipped the issue
        return True, ["  No artifacts declared"]   # the runtime gate passed it

Enforcement was therefore monotonic in honesty: declare nothing and the gate
skips you entirely, declare truthfully and every entry is checked against git
and can fail. The check also ran in ONE direction only -- declared -> exists --
so it could confirm that every claimed path was real and could never notice a
real change that was never claimed.

This module is the single answer to both questions, for both enforcers:

* ``coach.issue.artifact-claims-must-resolve`` (strict) -- every declared path
  resolves against git at the point in history that carries the work;
* ``coach.issue.artifacts-must-be-declared`` (advisory, ratcheting) -- the
  section is a COMPLETE record: non-empty, and naming every changed file.

Both ids are resolved through ``bind_rule`` at module-import time, so severity
and disposition come from ``issue.convention.yaml`` rather than being hard-coded
here (SPEC-COACH-RULEID-0007). Callers supply the git facts -- a ``resolves``
probe and the changed-file set -- so the policy stays pure and testable while
the revision arithmetic stays with the caller that already owns it (#1611).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from atdd.coach.utils.rule_binding import RuleMetadata, bind_rule
from atdd.coach.validators._violation import Violation

# coach → planner, never the reverse: the issue-body schema is planner-owned and
# is the single place that says what a repo-relative path looks like. Reading it
# here is what keeps the gate's idea of "a path" and the authoring path's idea of
# "a path" the same idea (#1726).
from atdd.planner.commands.author_issue import is_repo_relative_path

# ---------------------------------------------------------------------------
# Convention binding
# ---------------------------------------------------------------------------
RULE_CLAIMS_RESOLVE = "coach.issue.artifact-claims-must-resolve"
RULE_MUST_BE_DECLARED = "coach.issue.artifacts-must-be-declared"

#: Every rule this module can emit, resolved at import time. A rule that is not
#: declared in a convention raises ``RuleNotInRegistryError`` here -- loudly, at
#: import -- rather than at the moment a gate happens to run.
BOUND_RULES: Dict[str, RuleMetadata] = {
    rule_id: bind_rule(rule_id)
    for rule_id in (RULE_CLAIMS_RESOLVE, RULE_MUST_BE_DECLARED)
}

#: Stable name for the disposition gate's failure messages and warnings.
VALIDATOR_ID = "issue_gate_artifact_claims"

#: The subsections of ``## Artifacts``, in the order they are reported.
KINDS: Tuple[str, str, str] = ("created", "modified", "deleted")

# kind -> (message prefix, satisfied word, unsatisfied word). The git question
# each kind asks -- and the revision it asks it of -- belongs to the caller's
# ``resolves`` probe; this table is only how the answer is rendered.
_RENDERING = {
    "created": ("  Created:  ", "EXISTS", "MISSING"),
    "modified": ("  Modified: ", "CHANGED", "NO CHANGES"),
    "deleted": ("  Deleted:  ", "CONFIRMED GONE", "STILL EXISTS"),
}

#: The subsection a changed path is reported as missing from, when the reverse
#: pass finds it. Deletions are recognisable from the diff; everything else is
#: reported generically because the claim is what is absent, not the path.
_UNDECLARED_HINT = "declare it under ### Created, ### Modified or ### Deleted"


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ArtifactClaimReport:
    """What the checker found, in both machine and human form.

    ``violations`` routes to ``assert_disposition_satisfied`` in CI; ``messages``
    is what the CLI prints. Both enforcers read the same object, so the two can
    no longer disagree about what the section says.
    """

    violations: Tuple[Violation, ...]
    messages: Tuple[str, ...]

    @property
    def blocking(self) -> Tuple[Violation, ...]:
        """The violations whose rule disposition actually blocks.

        An ``advisory`` rule is reported and does not block; anything else does.
        A rule missing from the registry cannot happen here (``BOUND_RULES`` is
        resolved at import) but defaults to blocking for the same reason
        ``disposition_gate`` does.
        """
        return tuple(
            v for v in self.violations
            if (BOUND_RULES[v.rule_id].disposition or "strict") != "advisory"
        )

    @property
    def satisfied(self) -> bool:
        """Whether the gate passes -- decided by the convention, not by this code."""
        return not self.blocking


# ---------------------------------------------------------------------------
# The policy
# ---------------------------------------------------------------------------
def check_artifact_claims(
    artifacts: Mapping[str, Sequence[str]],
    *,
    resolves: Callable[[str, str], bool],
    changed_files: Optional[Iterable[str]] = None,
    issue_number: Optional[int] = None,
    against: str = "",
    force: bool = False,
) -> ArtifactClaimReport:
    """Check an issue's parsed ``## Artifacts`` claims. The only implementation.

    Args:
        artifacts: The parsed claims, keyed by :data:`KINDS` -- what
            ``IssueManager._parse_artifacts`` returns.
        resolves: ``resolves(kind, path) -> bool``, the git probe. True means
            git agrees with the claim (created exists / modified changed /
            deleted is gone). The caller owns which revision is asked, because
            that depends on whether the work has landed yet (#1611).
        changed_files: Every path the work touched, for the reverse pass. ``None``
            means "not asked" -- NOT "nothing changed". Post-merge with no landed
            commit resolvable, ``main...HEAD`` is empty by construction, and
            reading that as an empty change set would invent a violation for
            every declared path.
        issue_number: Reported in the violation location when known.
        against: Human suffix for the unsatisfied messages ("vs main" / "in
            ab12cd34"), matching what the caller probed.
        force: Skip the git probes and report each claim as skipped, as
            ``--force`` has always done. The declaration-completeness rule still
            applies -- ``--force`` waives verification, not the record.

    Returns:
        An :class:`ArtifactClaimReport`. Pass ``.violations`` to the disposition
        gate; print ``.messages``; read ``.satisfied`` for a bool verdict.
    """
    location = f"github-issue#{issue_number}:## Artifacts" if issue_number else "issue-body:## Artifacts"
    declared = {path for kind in KINDS for path in artifacts.get(kind, ())}
    violations: List[Violation] = []
    messages: List[str] = []

    if not declared:
        # The escape that used to live here, twice. An absent or bulletless
        # section is the empty set -- a determinable answer, not an unobservable
        # one -- so it resolves to a violation rather than to a free pass.
        violations.append(
            _violation(
                RULE_MUST_BE_DECLARED,
                location,
                "declares no artifacts; an empty `## Artifacts` section is not an "
                "exemption from the COMPLETE gate. Derive the record with "
                "`git diff --name-only origin/main..HEAD`.",
            )
        )
        messages.append("  No artifacts declared — the section is empty")
        # The per-file reverse pass would restate this once per changed file;
        # the empty declaration already says it once, better.
        return ArtifactClaimReport(tuple(violations), tuple(messages))

    for kind in KINDS:
        prefix, satisfied_word, unsatisfied_word = _RENDERING[kind]
        for path in artifacts.get(kind, ()):
            if force:
                messages.append(f"{prefix}{path} — SKIPPED (--force)")
                continue
            if resolves(kind, path):
                messages.append(f"{prefix}{path} — {satisfied_word}")
                continue
            suffix = f" {against}" if against else ""
            messages.append(f"{prefix}{path} — {unsatisfied_word}{suffix}")
            # Two very different repairs wear the same "MISSING" label: a path
            # that git disagrees with (stale, renamed, wrong subsection) and a
            # bullet that was never a path at all. Say which, using the schema's
            # own definition rather than a second opinion invented here.
            if is_repo_relative_path(path):
                detail = (
                    f"{kind} claim {path!r} does not resolve against git "
                    f"({unsatisfied_word}{suffix}) — the path is stale, renamed, "
                    f"or filed under the wrong subsection."
                )
            else:
                detail = (
                    f"{kind} claim {path!r} is prose, not a repo-relative path "
                    f"(issue.schema.json definitions.repoRelativePath), so it "
                    f"resolves against nothing. Name the file, or use the "
                    f"explicit-empty form `- (none yet)`."
                )
            violations.append(_violation(RULE_CLAIMS_RESOLVE, location, detail))

    if changed_files is not None:
        for path in sorted(set(changed_files) - declared):
            messages.append(f"  Undeclared: {path} — CHANGED BUT NOT CLAIMED")
            violations.append(
                _violation(
                    RULE_MUST_BE_DECLARED,
                    location,
                    f"{path!r} was changed by this work and never declared — "
                    f"{_UNDECLARED_HINT}.",
                )
            )

    return ArtifactClaimReport(tuple(violations), tuple(messages))


def _violation(rule_id: str, location: str, detail: str) -> Violation:
    """A ``Violation`` whose severity is the convention's, never this module's."""
    return Violation(
        rule_id=rule_id,
        severity=BOUND_RULES[rule_id].severity,
        location=location,
        detail=detail,
    )


__all__ = [
    "ArtifactClaimReport",
    "BOUND_RULES",
    "KINDS",
    "RULE_CLAIMS_RESOLVE",
    "RULE_MUST_BE_DECLARED",
    "VALIDATOR_ID",
    "check_artifact_claims",
]
