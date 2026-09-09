"""Declaration integrity — the half of the documentation obligation core decides alone.

A documentation declaration has exactly two total forms:

    {"impact": "change", "artifacts": [{"action": ..., "path": ...}, ...]}
    {"impact": "none",   "reason": "<why nothing changed>"}

Anything else is malformed, and a malformed declaration is not an absent obligation —
it is one whose author did not finish stating it.

FORMAT-AGNOSTIC BY CONSTRUCTION. Declared paths are opaque strings. Nothing here opens a
file, reads content, or interprets a path segment: core holds the obligation without
holding any documentation policy, which is what lets a consumer install the lifecycle
without inheriting an opinion about AsciiDoc, ADRs or a taxonomy. The rules that DO know
what a document is live in `atdd.extension.planner.docs`.

THIS IS ALSO THE GATE ON DELEGATION. The installed capability answers an absent
declaration `COULD_NOT_CHECK`, which blocks, and no stored work item carries a
declaration yet — so delegating before this check has run would refuse every COMPLETE in
the repository. `should_delegate` is that gate, and it is a separate, testable decision
rather than an implicit consequence of call order.
"""
from __future__ import annotations

from dataclasses import dataclass, field

KNOWN_IMPACTS = ("change", "none")


@dataclass(frozen=True)
class DeclarationCheck:
    """What core decided about a declaration, without reading any documentation.

    ``complete``   the declaration is one of the two total forms, fully stated.
    ``discharged`` complete AND every declared path appears in the change set.
    ``findings``   human-readable; each names what is missing or which path was not
                   touched. Never empty when ``complete`` or ``discharged`` is False —
                   a refusal that says nothing is the failure mode this check exists to
                   avoid.
    """

    complete: bool
    discharged: bool
    findings: list[str] = field(default_factory=list)


def _artifacts(declaration: dict | None) -> list[dict]:
    artifacts = (declaration or {}).get("artifacts")
    return [a for a in artifacts if isinstance(a, dict)] if isinstance(artifacts, list) else []


def check_declaration_integrity(
    declaration: dict | None, change_set: list[str] | None
) -> DeclarationCheck:
    """Decide whether a declaration is well-formed and its named artifacts were touched.

    An ABSENT declaration is not `impact: none`: the first is core having nothing to
    read, the second is an author considering the question and answering it. They are
    kept apart here for the same reason the capability keeps them apart downstream.
    """
    if declaration is None:
        return DeclarationCheck(
            complete=False,
            discharged=False,
            findings=["no documentation declaration was supplied; an absent declaration is "
                      "not `impact: none`, which is a positive statement that nothing changed"],
        )

    impact = declaration.get("impact")
    if impact not in KNOWN_IMPACTS:
        return DeclarationCheck(
            complete=False,
            discharged=False,
            findings=[f"declaration carries impact={impact!r}; the two total forms are "
                      f"`change` (with artifacts) and `none` (with a reason)"],
        )

    if impact == "none":
        # Core enforces that a reason is PRESENT. Core does not judge whether it is any
        # good, and neither does the extension.
        if not str(declaration.get("reason") or "").strip():
            return DeclarationCheck(
                complete=False,
                discharged=False,
                findings=["`impact: none` carries no reason; declaring that nothing changed "
                          "is a claim, and the claim must say why"],
            )
        return DeclarationCheck(complete=True, discharged=True)

    artifacts = _artifacts(declaration)
    if not artifacts:
        return DeclarationCheck(
            complete=False,
            discharged=False,
            findings=["`impact: change` names no artifacts; a declared change with nothing "
                      "declared is not a finished declaration"],
        )

    # Well-formed from here. Whether it is DISCHARGED is a separate question, answered
    # by comparing declared paths against the change set — string comparison only.
    touched = set(change_set or [])
    findings: list[str] = []
    for index, artifact in enumerate(artifacts):
        path = artifact.get("path")
        if not isinstance(path, str) or not path.strip():
            findings.append(f"artifact[{index}] declares no path")
            continue
        if path not in touched:
            findings.append(
                f"declared artifact {path!r} is not in the change set, so the obligation "
                f"it names was not discharged"
            )
    return DeclarationCheck(complete=not any("declares no path" in f for f in findings),
                            discharged=not findings, findings=findings)


def should_delegate(check: DeclarationCheck) -> bool:
    """Whether core may hand this declaration to an installed capability.

    Delegation begins only once the declaration is well-formed. Handing an incomplete or
    absent declaration to the capability yields COULD_NOT_CHECK, which blocks — correct
    of the capability, and useless as a report, because the fault is core's to name.
    """
    return check.complete
