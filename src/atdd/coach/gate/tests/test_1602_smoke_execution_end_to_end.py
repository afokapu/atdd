# Phase: SMOKE
# Layer: e2e
# Assertion: behavioral
"""#1602 SMOKE — the whole chain, through the real path, in both directions.

Everything else in this issue is tested against a seam. This file is the only
proof that the seams are connected, and it is deliberately the least mocked
thing in the change: it builds a real git repository with a real ``plan/``
declaring a real ``execution_kind: live_smoke`` acceptance, runs **pytest in a
subprocess** over it, and then asks the real ``SmokeExecutionGateCheck`` what it
thinks. Nothing between the test running and the gate deciding is stubbed —
the attestation that reaches the gate is the one the pytest hook wrote.

    a live-smoke test that RUNS and PASSES  -> attestation written -> gate PASSES
    a live-smoke test that is SKIPPED       -> skip recorded       -> gate FAILS
    a live-smoke test that never runs       -> nothing recorded    -> gate FAILS

The first line is the negative control and it is the one that matters. A gate
that refuses everything satisfies the other two and is worthless — that is the
failure mode this whole issue exists to remove, and reproducing it in the test
suite would be the same mistake one level up.

Two further rows go beyond the brief because the record would otherwise be
decorative: the attestation must actually *carry* what it claims (commit,
execution kind, acceptance urn), and it must go stale — smoke run at commit A
must not license a transition at commit B.

HOW THE SUBPROCESS REACHES THE HOOK — and why that detail is the whole test.
The attestation writer is attached by the substrate plugin's
``pytest_configure``, and the substrate plugin is auto-loaded by pytest from the
``pytest11`` **entry point** declared in ``pyproject.toml``. Entry points are read
from *installed distribution metadata*, never from ``sys.path``/``PYTHONPATH``.
A consumer has that metadata because they ran ``pip install atdd``; this repo's
own CI does not, because every job runs ``PYTHONPATH=src python3 -m pytest``
against an uninstalled tree. So a subprocess given only ``PYTHONPATH`` imports
``atdd`` fine and never loads the plugin — the run is green, records nothing, and
these tests fail.

Handing the subprocess ``-p atdd.tester.substrate.plugin`` would make them pass
while proving nothing about a real consumer. Instead
:func:`~atdd.coach.gate.live_smoke.installed_metadata` materializes the
``.dist-info`` that ``pip install`` would have produced, with the entry points
read out of **this repo's ``pyproject.toml``** — so the subprocess discovers and
loads the plugin through the ordinary
``importlib.metadata`` → ``load_setuptools_entrypoints("pytest11")`` path, and
deleting the declaration from ``pyproject.toml`` turns this file red.

WHERE THE MACHINERY LIVES. The fixture repository, the synthesized metadata and
the subprocess invocation are NOT defined here — they are the shipped live-smoke
harness :mod:`atdd.coach.gate.live_smoke`, which the ``E069-SMOKE-001``
acceptance's anchored test drives as well. One definition, two callers: if this
file forked its own copy, the acceptance and this e2e could pass against
different chains.

What the suite cannot do to itself — pip-install a wheel per test — was done
once by hand: a wheel built from this branch, installed into a clean venv with
no ``PYTHONPATH`` and no source tree in sight, ran an anchored probe in a
fixture consumer repo and wrote exactly one ``passed`` attestation, which opened
the gate; the same probe skipped recorded a ``skipped`` and closed it. The half
of that which IS mechanized lives in
``test_the_hook_is_activated_by_the_pytest11_entry_point_this_repo_declares``.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from atdd.coach.gate.live_smoke import (
    ACCEPTANCE_URN,
    PROBE_THAT_DOES_NOT_EXECUTE,
    PROBE_THAT_RUNS,
    PROBE_WITHOUT_ANCHOR,
    attested_runs,
    build_probe_repo,
    declared_pytest11_entry_points,
    gate_verdict,
    git,
    run_probe_pytest,
)

pytestmark = [pytest.mark.platform, pytest.mark.smoke]

#: Local alias: from this file's point of view the interesting property of that
#: probe is that it SKIPS — the harness names it for what it fails to do.
PROBE_THAT_SKIPS = PROBE_THAT_DOES_NOT_EXECUTE


@pytest.fixture(autouse=True)
def _isolate_control_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Keep this test's store reads inside tmp_path, never the developer's."""
    monkeypatch.setenv("ATDD_CONTROL_ROOT", str(tmp_path / "probe-repo"))


# --------------------------------------------------------------------------- #
# The activation path — how a consumer's pytest ever reaches the hook          #
# --------------------------------------------------------------------------- #


def test_the_hook_is_activated_by_the_pytest11_entry_point_this_repo_declares(
    tmp_path: Path,
) -> None:
    """An attestation nobody's pytest loads is inert in every consumer.

    Two claims, because the second is worthless without the first:

    1. ``pyproject.toml`` declares the substrate plugin under ``pytest11``. That
       declaration IS the activation mechanism in an installed consumer, and it
       is what the rest of this file's subprocesses are handed as metadata.
    2. Blocking that entry point *by name* takes the attestation with it. So the
       record the other tests observe arrives through the plugin pytest loaded
       from the declaration, not through some other route the harness supplied.

    The remaining gap — that real installed metadata behaves like the metadata
    this file synthesizes — cannot be closed inside the suite without a per-test
    ``pip install``. It was closed by hand instead; see the module docstring.
    """
    entry_points = declared_pytest11_entry_points()
    assert "atdd.tester.substrate.plugin" in entry_points.values(), (
        "the substrate plugin is no longer declared as a pytest11 entry point — "
        "nothing auto-loads the smoke attestation in an installed consumer, and "
        f"the whole gate is inert. declared: {entry_points}"
    )

    repo = build_probe_repo(tmp_path, PROBE_THAT_RUNS)

    blocked = run_probe_pytest(repo, "-p", "no:atdd_substrate")
    assert blocked.returncode == 0, f"the probe suite failed:\n{blocked.stdout}"
    assert attested_runs(repo) == [], (
        "an attestation appeared with the substrate entry point blocked — the "
        "harness, not the entry point, is loading the hook"
    )

    assert run_probe_pytest(repo).returncode == 0
    assert len(attested_runs(repo)) == 1, "the same run, unblocked, must attest"


# --------------------------------------------------------------------------- #
# Direction 1 — it really ran: the negative control                            #
# --------------------------------------------------------------------------- #


def test_a_live_smoke_run_that_passes_writes_an_attestation_and_opens_thegate_verdict(
    tmp_path: Path,
) -> None:
    """The whole chain, forward: pytest ran -> store recorded -> gate PASSES."""
    repo = build_probe_repo(tmp_path, PROBE_THAT_RUNS)
    assert not gate_verdict(repo).passed, (
        "the gate was already open before smoke ran — nothing below would mean anything"
    )

    result = run_probe_pytest(repo)
    assert result.returncode == 0, f"the probe suite failed:\n{result.stdout}\n{result.stderr}"

    runs = attested_runs(repo)
    assert len(runs) == 1, (
        f"the pytest hook recorded {len(runs)} run(s), expected exactly the anchored "
        f"probe — unanchored tests must not be attested. stdout:\n{result.stdout}"
    )
    assert runs[0].outcome == "passed"
    assert runs[0].duration_s > 0.0, "a run with no measured duration did not execute"
    assert runs[0].nodeid.endswith("test_live_smoke_probe")

    verdict = gate_verdict(repo)
    assert verdict.passed, f"smoke really ran and the gate still refused: {verdict.message}"


def test_the_attestation_carries_what_it_claims(tmp_path: Path) -> None:
    """A record that names neither the code nor the claim is decoration."""
    repo = build_probe_repo(tmp_path, PROBE_THAT_RUNS)
    run_probe_pytest(repo)

    run = attested_runs(repo)[0]

    assert run.commit_sha == git(repo, "rev-parse", "HEAD"), (
        "the attestation must name the commit it exercised, or staleness is unknowable"
    )
    assert run.execution_kind == "live_smoke"
    assert run.acceptance_urn == ACCEPTANCE_URN, (
        "the run must be traceable back to the planner acceptance it discharges"
    )


# --------------------------------------------------------------------------- #
# Direction 2 — it did not run                                                 #
# --------------------------------------------------------------------------- #


def test_a_skipped_live_smoke_test_is_recorded_as_a_skip_and_closes_thegate_verdict(
    tmp_path: Path,
) -> None:
    """#1076, closed: the skip is visible AND it does not satisfy the gate.

    Both halves matter. Recording nothing would also block the gate, but it
    would leave an operator unable to tell "smoke was skipped" from "smoke was
    never attempted" — which is precisely how C010-SMOKE-001 looked green.
    """
    repo = build_probe_repo(tmp_path, PROBE_THAT_SKIPS)

    result = run_probe_pytest(repo)
    assert result.returncode == 0, "a skipped test is not a suite failure"

    runs = attested_runs(repo)
    assert [r.outcome for r in runs] == ["skipped"], (
        f"the skip must be written down, loudly. stdout:\n{result.stdout}"
    )

    verdict = gate_verdict(repo)
    assert not verdict.passed, "a skipped live-smoke test satisfied the smoke gate"
    assert "skipped" in verdict.message


def test_a_live_smoke_test_that_never_runs_leaves_no_attestation_and_closes_thegate_verdict(
    tmp_path: Path,
) -> None:
    """Deselected, not executed, nothing recorded — and still blocked.

    The suite is green (it ran, and everything it selected passed), so this is
    the case a "did the tests pass?" gate waves through and an execution gate
    must not.
    """
    repo = build_probe_repo(tmp_path, PROBE_THAT_RUNS)

    result = run_probe_pytest(repo, "tests/test_unanchored.py")
    assert result.returncode == 0, f"the unanchored suite should pass:\n{result.stdout}"

    assert attested_runs(repo) == [], "a test that never ran must attest nothing"

    verdict = gate_verdict(repo)
    assert not verdict.passed, (
        "a green pytest run that never executed the live-smoke test opened the gate"
    )
    assert "no smoke-execution attestation" in verdict.message


# --------------------------------------------------------------------------- #
# The ratchet — evidence about other code is not evidence about this code      #
# --------------------------------------------------------------------------- #


def test_an_attestation_goes_stale_when_the_code_moves_on(tmp_path: Path) -> None:
    """Smoke run at commit A must not license a transition at commit B."""
    repo = build_probe_repo(tmp_path, PROBE_THAT_RUNS)
    run_probe_pytest(repo)
    assert gate_verdict(repo).passed, "precondition: the fresh attestation opens the gate"

    (repo / "tests" / "test_unanchored.py").write_text(
        PROBE_WITHOUT_ANCHOR + "\n\ndef test_added_later():\n    assert True\n"
    )
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "change the code after smoking it")

    verdict = gate_verdict(repo)
    assert not verdict.passed, (
        "the gate accepted smoke evidence captured against different code"
    )
    assert "not at HEAD" in verdict.message
