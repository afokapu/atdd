# URN: test:govern-documentation-obligation:delegate-content-judgement:C001-UNIT-002-absent-capability-is-not-applicable
# Acceptance: acc:govern-documentation-obligation:C001-UNIT-002-absent-capability-is-not-applicable
# WMBT: wmbt:govern-documentation-obligation:C001
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""C001-UNIT-002 — no capability installed is NOT_APPLICABLE, and it permits.

This is the boundary's whole point. A consumer who installs ATDD core and no
documentation extension gets the lifecycle obligation and no opinion about AsciiDoc,
ADRs or a taxonomy. If an absent capability blocked, core would be forcing a
documentation system on every consumer by omission — the opposite of what shipping the
policy as an extension is for.

The distinction from COULD_NOT_CHECK is the load-bearing part and is asserted directly:
*there is nothing here to judge* and *I could not judge what is here* are different
facts, and only the first may permit.
"""
from __future__ import annotations

from atdd.coach.documentation import DocumentationCheck, Finding, judge_documentation, verdict

_WELL_FORMED = {"impact": "change", "artifacts": [{"action": "create", "path": "docs/x.adoc"}]}


class _Raising:
    """A capability that fails, standing in for one that is installed but broken."""

    def check(self, declaration, change_set, repo_root):
        raise RuntimeError("asciidoctor exploded")


class _Answering:
    def __init__(self, value: str) -> None:
        self._value = value

    def check(self, declaration, change_set, repo_root):
        return DocumentationCheck(
            verdict=self._value,
            findings=[Finding("planner.docs.capability", "<declaration>", "why")],
            checked=["docs/x.adoc"],
        )


def test_no_capability_installed_is_not_applicable_and_permits() -> None:
    outcome = judge_documentation(_WELL_FORMED, ["docs/x.adoc"], ".", capability=None)

    # `capability=None` with none installed in this interpreter is the absent case.
    assert outcome.verdict == verdict.NOT_APPLICABLE
    assert verdict.blocks(outcome.verdict) is False
    assert outcome.findings == []
    assert outcome.checked == [], "nothing was examined, and `checked` must not claim otherwise"


def test_not_applicable_is_distinguishable_from_could_not_check() -> None:
    absent = judge_documentation(_WELL_FORMED, ["docs/x.adoc"], ".", capability=None)
    unobservant = judge_documentation(
        _WELL_FORMED, ["docs/x.adoc"], ".", capability=_Answering(verdict.COULD_NOT_CHECK)
    )

    assert absent.verdict != unobservant.verdict
    assert verdict.blocks(absent.verdict) is False
    assert verdict.blocks(unobservant.verdict) is True


def test_an_installed_capability_that_raises_is_a_failure_not_an_absence() -> None:
    """A broken capability is present. Reading it as absent would permit on a fault."""
    outcome = judge_documentation(_WELL_FORMED, ["docs/x.adoc"], ".", capability=_Raising())

    assert outcome.verdict == verdict.FAIL
    assert verdict.blocks(outcome.verdict) is True
    assert any("asciidoctor exploded" in f.message for f in outcome.findings)


def test_a_pass_relays_the_capabilitys_own_account_of_what_it_examined() -> None:
    outcome = judge_documentation(
        _WELL_FORMED, ["docs/x.adoc"], ".", capability=_Answering(verdict.PASS)
    )

    assert outcome.verdict == verdict.PASS
    assert verdict.blocks(outcome.verdict) is False
    assert outcome.checked == ["docs/x.adoc"], "core relays `checked`, it does not invent it"


def test_an_unknown_verdict_blocks() -> None:
    """A vocabulary core does not recognise is itself an unobserved state."""
    outcome = judge_documentation(
        _WELL_FORMED, ["docs/x.adoc"], ".", capability=_Answering("PROBABLY_FINE")
    )

    assert verdict.blocks(outcome.verdict) is True
