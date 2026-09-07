"""The seam: resolve at most one installed documentation capability, and read its answer.

Core delegates every judgement about what a document IS. It resolves the capability
over an entry-point group and names no concrete extension — the whole point of the
boundary is that a consumer who installs no documentation extension keeps a working
lifecycle.

WIRE TYPES, NOT CORE DATACLASSES. The capability is called with `declaration` as a
plain ``dict | None`` and `change_set` as a plain ``list[str] | None`` because the
installed implementation calls ``declaration.get(...)``. Handing it a core dataclass
breaks the seam silently at runtime, which is a mistake this contract made on paper
before it was read against the shipped source.

``None`` IS NOT ``[]``. The capability treats a ``None`` change set as
COULD_NOT_CHECK — "core did not tell me what changed" — while ``[]`` is "core told me,
and nothing changed". Core must preserve that distinction rather than normalising on
the way out.

INTEGRITY BEFORE DELEGATION IS THE CALLER'S JOB, AND IT IS NOT OPTIONAL. This module
does the seam and nothing else. The gate that decides whether to delegate at all —
`should_delegate` over `check_declaration_integrity` — is #1797's deliverable, and the
COMPLETE gate composes the two.

The separation is deliberate rather than incidental: the two halves are different
obligations owned by different issues, and one issue binds one feature. But the
composition is load-bearing. The capability answers an absent or malformed declaration
COULD_NOT_CHECK, which blocks, and no stored work item carries a declaration yet — so
a caller that delegates without gating first refuses every COMPLETE in the repository,
and reports core's own omission as the extension's blindness.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Sequence

from . import verdict as _verdict

#: The entry-point group core discovers. Never a concrete extension id.
ENTRY_POINT_GROUP = "atdd.documentation"

#: Findings core raises itself, as opposed to relaying from the capability.
SEAM_RULE_ID = "coach.documentation.seam"


@dataclass(frozen=True)
class Finding:
    """Human-readable, and it always names a path or a document identity.

    Shape matches the installed capability's `Finding` exactly, verified against
    `atdd.extension.planner.docs`: relaying its findings must not reshape them.
    """

    rule_id: str
    where: str
    message: str

    def __str__(self) -> str:
        return f"{self.where}: {self.message} [{self.rule_id}]"


@dataclass(frozen=True)
class DocumentationCheck:
    """The value core reads back. Shape is fixed by THE BINDING."""

    verdict: str
    findings: list = field(default_factory=list)
    checked: list = field(default_factory=list)


def resolve_documentation_capability() -> Optional[Any]:
    """The one installed capability, or None.

    More than one installed is ambiguous, not a majority vote: core cannot choose
    between two documentation policies, and silently picking the first would make the
    answer depend on entry-point ordering.
    """
    try:
        from importlib.metadata import entry_points

        found = list(entry_points(group=ENTRY_POINT_GROUP))
    except Exception:  # pragma: no cover - importlib shape varies by runtime
        return None
    if len(found) != 1:
        return None
    try:
        return found[0].load()()
    except Exception:
        # A capability that cannot even be constructed is not an absent one. The
        # caller turns this into FAIL rather than NOT_APPLICABLE.
        raise


def judge_documentation(
    declaration: Optional[dict],
    change_set: Optional[Sequence[str]],
    repo_root: "Path | str",
    capability: Optional[Any] = None,
) -> DocumentationCheck:
    """Core's answer for one work item's documentation obligation.

    PRECONDITION: the declaration has already passed integrity (#1797's
    `should_delegate`). This function does not re-check it — see the module
    docstring for why delegating an unchecked declaration is a repo-wide refusal.

    ``capability`` is injectable so the seam can be exercised without an installed
    extension; when omitted it is resolved over the entry-point group.
    """
    if capability is None:
        try:
            capability = resolve_documentation_capability()
        except Exception as exc:  # a capability that fails to load is not an absent one
            return DocumentationCheck(
                verdict=_verdict.FAIL,
                findings=[Finding(SEAM_RULE_ID, ENTRY_POINT_GROUP,
                                  f"the installed documentation capability could not be loaded: {exc!r}")],
                checked=[],
            )

    if capability is None:
        # Genuinely nothing to judge. This is the boundary's whole point: core must
        # not force a documentation system onto a consumer that installed none.
        return DocumentationCheck(verdict=_verdict.NOT_APPLICABLE, findings=[], checked=[])

    try:
        answer = capability.check(
            declaration,
            list(change_set) if change_set is not None else None,
            Path(repo_root),
        )
    except Exception as exc:  # noqa: BLE001 — a raising capability is a FAIL, never a pass
        return DocumentationCheck(
            verdict=_verdict.FAIL,
            findings=[Finding(SEAM_RULE_ID, ENTRY_POINT_GROUP,
                              f"the documentation capability raised: {exc!r}")],
            checked=[],
        )

    return DocumentationCheck(
        verdict=getattr(answer, "verdict", _verdict.COULD_NOT_CHECK),
        findings=list(getattr(answer, "findings", []) or []),
        checked=list(getattr(answer, "checked", []) or []),
    )
