# URN: test:govern-documentation-obligation:check-declaration-integrity:D001-UNIT-002-declared-path-absent-from-change-set
# Acceptance: acc:govern-documentation-obligation:D001-UNIT-002-declared-path-absent-from-change-set
# WMBT: wmbt:govern-documentation-obligation:D001
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""D001-UNIT-002 — a declared artifact absent from the change set is not discharged.

This is the deterministic, format-free proof that an obligation was not met: the author
said they would touch these paths, and the diff does not contain them. It needs no
knowledge of what a document is, which is precisely why core can hold it.

The inverse — detecting that a change SHOULD have been declared — is semantic and not
deterministically decidable from here, so it is the extension's
`planner.docs.undeclared-change`, not core's.

The anti-theatre test at the bottom is load-bearing. The whole boundary rests on this
check being format-agnostic, and "we intended it to be" is not a property. A grep is.
"""
from __future__ import annotations

import inspect
import re

from atdd.coach.documentation import check_declaration_integrity, should_delegate
from atdd.coach.documentation import declaration as declaration_module


def test_a_declared_path_not_in_the_change_set_is_not_discharged() -> None:
    check = check_declaration_integrity(
        declaration={"impact": "change", "artifacts": [{"action": "create", "path": "docs/a.adoc"}]},
        change_set=["src/atdd/coach/gate/decision.py"],
    )

    assert check.complete is True, "the declaration is well-formed; only its discharge failed"
    assert check.discharged is False
    assert any("docs/a.adoc" in f for f in check.findings), (
        "the finding must name the path that was not touched"
    )


def test_a_declared_path_present_in_the_change_set_is_discharged() -> None:
    check = check_declaration_integrity(
        declaration={"impact": "change", "artifacts": [{"action": "create", "path": "docs/a.adoc"}]},
        change_set=["docs/a.adoc", "src/atdd/coach/gate/decision.py"],
    )

    assert check.complete is True
    assert check.discharged is True
    assert check.findings == []


def test_every_undischarged_path_is_named_not_just_the_first() -> None:
    check = check_declaration_integrity(
        declaration={
            "impact": "change",
            "artifacts": [
                {"action": "create", "path": "docs/a.adoc"},
                {"action": "modify", "path": "docs/b.adoc"},
            ],
        },
        change_set=["docs/a.adoc"],
    )

    assert check.discharged is False
    assert any("docs/b.adoc" in f for f in check.findings)
    assert not any("docs/a.adoc" in f for f in check.findings), (
        "a path that WAS touched must not be reported"
    )


def test_a_well_formed_declaration_may_be_delegated_even_when_undischarged() -> None:
    """Delegation is gated on well-formedness, not on discharge.

    An undischarged obligation is a finding core can state by itself. An incomplete
    declaration is one it cannot, so the capability must not be asked about it.
    """
    undischarged = check_declaration_integrity(
        declaration={"impact": "change", "artifacts": [{"action": "create", "path": "docs/a.adoc"}]},
        change_set=[],
    )
    incomplete = check_declaration_integrity(declaration={"impact": "none", "reason": ""}, change_set=[])
    absent = check_declaration_integrity(declaration=None, change_set=[])

    assert should_delegate(undischarged) is True
    assert should_delegate(incomplete) is False
    assert should_delegate(absent) is False


def test_the_check_reads_no_file_and_interprets_no_path_segment() -> None:
    """Anti-theatre: the boundary is a property of the source, so assert it there."""
    source = inspect.getsource(declaration_module)
    body = "\n".join(
        line for line in source.splitlines()
        if not line.lstrip().startswith("#")
    )
    body = re.sub(r'""".*?"""', "", body, flags=re.S)

    for forbidden in ("open(", "read_text", "Path(", "os.path", "glob", ".adoc", "docs/"):
        assert forbidden not in body, (
            f"declaration.py references {forbidden!r}; core must not learn what a "
            f"documentation file is — that knowledge belongs to the installed capability"
        )
