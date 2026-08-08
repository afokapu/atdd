# URN: test:govern-lifecycle:enforcing-phase-transition-gate:R011-SMOKE-001-consumer-repo-programmatic-transition-is-refused
# Acceptance: acc:govern-lifecycle:R011-SMOKE-001-consumer-repo-programmatic-transition-is-refused
# WMBT: wmbt:govern-lifecycle:R011
# Phase: SMOKE
# Layer: integration
# Smoke: true
# Assertion: behavioral
# Purpose: a real non-atdd repository advancing a phase across a gated edge through a programmatic, non-CLI path is REFUSED — the consumer inherits the enforcement, not only atdd
"""R011-SMOKE-001 — consumer-repo parity, on the programmatic path.

CONSUMER PARITY IS FIRST-CLASS HERE, NOT A FOLLOW-UP. A consumer repo drives
transitions through this same substrate and inherits the same fail-open. An
acceptance that only passes because it runs inside atdd is the defect, not the
evidence, so this test stands up a repository that is NOT atdd: its own path, its
own git repo, its own ``.atdd/`` Control Root, and — deliberately — NO
``gate.transitions`` config of its own, so ``PLANNED->RED`` is gated purely by the
``DEFAULT_GATED_TRANSITIONS`` a consumer inherits without configuring anything.

The advance goes through ``IssueLifecycle.transition`` — the PROGRAMMATIC path,
never the ``atdd coach transition`` verb. That is the whole point: the verb is the
one road that registers today.

WHAT IS REAL AND WHAT IS NOT. Everything on the decision path is real and
unmocked: the enforcement seam, the registration, ``GATE_REGISTRY``,
``is_transition_gated``, ``ApprovalTokenGateCheck``, ``locate_approval_token``,
and the real ``apply_transition`` orchestration. The SINGLE stub is the GitHub
CLI, because ``_fetch_issue`` shells out to ``gh`` to learn the from-phase. An
absent ``gh`` would make the transition refuse for the WRONG reason — a fetch
failure wearing the gate's exit code — which is precisely the theater this
acceptance must not be. The stub is a real executable on ``PATH`` answering with a
canned issue, so the boundary shape (subprocess, argv, JSON on stdout) is real
too.

THE DISCRIMINATOR IS THE RULE-ID ATTRIBUTION. Asserting only "non-zero" would
pass on a missing ``gh``, on a bad layout, or inside atdd for reasons that do not
transfer to a consumer. The refusal must name
``govern-lifecycle.E050.operator-approval-required``.

NO TOKEN IS MINTED HERE. The mint side is #1670's, and this test asserts the
CONSULT side only.

RED state: the consumer's programmatic transition sails through the gated edge,
because the registry is empty on every path but the CLI verb's and an empty
registry returns 0.
"""
from __future__ import annotations

import json
import os
import stat
import subprocess
from pathlib import Path

import pytest

from atdd.coach.gate.approval_check import RULE_ID as APPROVAL_RULE_ID

pytestmark = [pytest.mark.platform, pytest.mark.smoke]

# Never a live issue in any repo: the fixture's own throwaway number.
_ISSUE = 999014

# The canned body is TEMPLATE-COMPLIANT on purpose. `apply_transition` runs the
# transition gate first and the compliance gate second, so a stub body would let
# the compliance gate refuse and mask whatever the transition gate did — measured
# on this exact fixture: with a stub body the refusal reads "template
# non-compliant", and the gate had already returned 0 through the fail-open. A
# consumer-parity smoke that cannot tell those two refusals apart proves nothing,
# which is why the rule-id assertion below is the real subject of this test.
_COMPLIANT_BODY = "\n".join(
    ["# consumer repo work item", ""]
    + [
        line
        for section in (
            "Issue Metadata", "Scope", "Context", "Architecture", "Phases",
            "Validation", "Decisions", "Activity Log", "Artifacts",
            "Release Gate", "Notes",
        )
        for line in (f"## {section}", "", "Real content for the fixture.", "")
    ]
    + ["### Graph Context", "", "Real content for the fixture.", ""]
    + ["### Mirror Across Agents", "", "Real content for the fixture.", ""]
)

_CANNED_ISSUE = {
    "number": _ISSUE,
    "title": "consumer repo work item",
    "state": "OPEN",
    "labels": [{"name": "atdd-issue"}, {"name": "atdd:PLANNED"}],
    "body": _COMPLIANT_BODY,
}


@pytest.fixture
def consumer_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A real repository that is NOT atdd, with a real `gh` stub on PATH."""
    repo = tmp_path / "some-consumer-product"
    (repo / ".atdd" / "state").mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)

    # No `gate:` block at all — the consumer inherits PLANNED->RED from
    # DEFAULT_GATED_TRANSITIONS without configuring anything. That inheritance is
    # the property under test; writing `PLANNED->RED: true` here would prove only
    # that an explicitly-configured repo is gated.
    (repo / ".atdd" / "config.yaml").write_text(
        "version: '1.0'\ngithub:\n  repo: someorg/some-consumer-product\n"
    )

    # The one stubbed boundary: a REAL executable answering `gh issue view`.
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    # Records every argv it is handed, so a write ATTEMPT is observable rather
    # than merely un-echoed. An unreachable stub cannot distinguish "issued a
    # label edit that failed" from "never issued one", and the second is the
    # property under test.
    argv_log = tmp_path / "gh-argv.log"
    gh.write_text(
        "#!/bin/sh\n"
        f'printf "%s\\n" "$*" >> "{argv_log}"\n'
        'if [ "$1" = "issue" ] && [ "$2" = "view" ]; then\n'
        f"  cat <<'JSON'\n{json.dumps(_CANNED_ISSUE)}\nJSON\n"
        "  exit 0\n"
        "fi\n"
        'echo "stub gh: unexpected call: $*" >&2\n'
        "exit 1\n"
    )
    gh.chmod(gh.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")

    # Signing key present, token absent: the check must fail on the MISSING
    # token, not on an unresolvable key.
    monkeypatch.setenv("ATDD_APPROVAL_SIGNING_KEY", "consumer-smoke-key")
    return repo


def test_consumer_repo_programmatic_transition_across_a_gated_edge_is_refused(
    consumer_repo: Path, capsys: pytest.CaptureFixture
):
    """R011-SMOKE-001: the consumer is refused, and the gate is why."""
    from atdd.coach.commands.issue_lifecycle import IssueLifecycle

    token_dir = consumer_repo / ".atdd" / "runtime"
    assert not list(token_dir.rglob("*.json")) if token_dir.exists() else True, (
        "precondition: no approval token anywhere under the consumer's Control Root"
    )

    # The PROGRAMMATIC path — never `atdd coach transition`.
    rc = IssueLifecycle(target_dir=consumer_repo).transition(_ISSUE, "RED")

    assert rc != 0, (
        "a consumer repo advanced PLANNED->RED with no operator approval token, "
        "through a path that never registers the gate checks. The consumer "
        "inherits the substrate, so it must inherit the refusal."
    )

    out = capsys.readouterr().out
    assert APPROVAL_RULE_ID in out, (
        f"the refusal must be attributed to {APPROVAL_RULE_ID} — otherwise a "
        f"fetch, layout or config error wearing the same exit code would satisfy "
        f"this test. Got:\n{out}"
    )
    assert "could not fetch issue" not in out, (
        "the gh stub failed to answer, so this refusal proves nothing about gates"
    )


def test_consumer_repo_refusal_lands_before_any_phase_write(
    consumer_repo: Path, tmp_path: Path
):
    """R011-SMOKE-001: a refused transition attempts no phase write at all.

    The refusal must land BEFORE ``IssueManager.update``'s label/phase swap, so
    the consumer's issue keeps the phase it had. Observed through the stub's
    recorded argv rather than through a re-read: a re-read of a stub that never
    mutates anything would report the original labels no matter what the code
    tried to do, and would pass just as happily while the gate was wide open.

    HONEST SCOPE: this is a REGRESSION GUARD, not RED evidence. In the RED state
    it passes for an incidental reason — the fail-open lets control reach
    ``IssueManager.update``, which then cannot build a GitHub client for the
    fixture repo and aborts before attempting any write. It earns its place from
    GREEN onward, where it pins the ordering that keeps a refused transition from
    ever reaching the label swap. The RED evidence for this acceptance is the
    rule-id assertion in the test above, which fails today because the gate
    returns 0 and never looks.
    """
    from atdd.coach.commands.issue_lifecycle import IssueLifecycle

    IssueLifecycle(target_dir=consumer_repo).transition(_ISSUE, "RED")

    argv_log = tmp_path / "gh-argv.log"
    calls = argv_log.read_text().splitlines() if argv_log.exists() else []
    assert calls, "the gh stub was never invoked — the fixture is not wired"

    writes = [c for c in calls if "issue edit" in c or "issue close" in c]
    assert not writes, (
        f"the refused transition still attempted a phase write: {writes}. The "
        f"gate must refuse before IssueManager.update reaches the label swap."
    )
