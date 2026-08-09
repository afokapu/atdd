"""acc:govern-registry:E004-SMOKE-001 — the predicate against real artifacts.

Fixtures prove the chain refuses. Only the real substrate proves it can be
SATISFIED: the toolkit's own committed ``.atdd/binding.lock.yaml``, its vendored
implementation manifests and report files, its vendored provider CLI on disk,
and the real ``.github`` workflow that decides whether Path B blocks. Nothing is
substituted, and nothing is skipped — every one of those artifacts is committed,
so this test has no reason to self-skip and is not permitted to.

A predicate that only ever passed against a substrate its own test wrote would
be the theatre program #1772 exists to prevent. This is the arm that would fail
if the live corpus could not actually satisfy the chain.
"""
from __future__ import annotations

import pytest
import yaml

from atdd.coach.utils.repo import find_repo_root
from atdd.coach.validators._bound_realization import (
    PROVEN,
    PROVEN_BASIS,
    BoundRealizationResolver,
)
from atdd.substrate.binding.plan import substrate_lock_digest

pytestmark = [pytest.mark.coach]

_REPO_ROOT = find_repo_root()


@pytest.fixture(scope="module")
def resolver() -> BoundRealizationResolver:
    return BoundRealizationResolver.for_repo(_REPO_ROOT)


@pytest.fixture(scope="module")
def real_lock(resolver) -> dict:
    assert resolver.lock_path.is_file(), (
        f"{resolver.lock_path} is the real substrate this acceptance is about; "
        f"it is committed, so its absence is a failure, never a skip"
    )
    return yaml.safe_load(resolver.lock_path.read_text(encoding="utf-8"))


def test_the_real_lock_is_digest_coherent_with_the_real_substrate(real_lock):
    """The live proof rests on a lock that still describes its substrate.

    This is load-bearing rather than incidental. Nothing else on ``origin/main``
    reads ``substrate_lock_digest`` — ``atdd enforce --verify-substrate`` checks
    PACKAGE digests, a different thing — so before this resolver existed the key
    could drift unnoticed, and it had: the committed plan was keyed to the
    substrate lock as of #1396 while the substrate lock itself last changed in
    #1606. Recomposing produced byte-identical conventions and only a new digest,
    which is why repairing it changed no enforcement.
    """
    assert real_lock["substrate_lock_digest"] == substrate_lock_digest(_REPO_ROOT), (
        "the committed binding lock no longer describes the substrate on disk — "
        "re-run `atdd bind --check`"
    )


def test_a_real_bound_rule_resolves_the_complete_chain(resolver, real_lock):
    """At least one REAL rule proves, carrying real artifact identities."""
    bound = [
        c["convention_id"]
        for c in real_lock["conventions"]
        if c.get("disposition") == "bound"
    ]
    assert bound, "the toolkit ships a populated binding lock; that is the premise"

    proven = [
        resolver.proof_for(rule_id)
        for rule_id in bound
        if resolver.proof_for(rule_id).outcome == PROVEN
    ]
    assert proven, (
        "no real bound rule resolves the complete chain — the predicate would "
        "then be satisfiable only by fixtures, which is exactly the theatre this "
        "program forbids. Refusals were: "
        + ", ".join(
            f"{resolver.proof_for(r).rule_id}:{resolver.proof_for(r).basis}"
            for r in bound
        )
    )

    for proof in proven:
        assert proof.basis == PROVEN_BASIS
        assert proof.discharges is True
        assert proof.verified is True
        # Real identities, resolved from real files — not defaults.
        assert proof.implementation_id
        assert proof.workspace_id
        assert proof.manifest_path is not None and proof.manifest_path.is_file()
        # The manifest really does sit inside the vendored substrate.
        assert ".atdd" in proof.manifest_path.parts


def test_the_real_provider_cli_and_report_channel_exist_on_disk(resolver, real_lock):
    """The runnable legs are file-system facts here, not fixture arrangements."""
    bound = [
        c for c in real_lock["conventions"] if c.get("disposition") == "bound"
    ]
    proven = [
        (c, resolver.proof_for(c["convention_id"]))
        for c in bound
        if resolver.proof_for(c["convention_id"]).outcome == PROVEN
    ]
    assert proven

    entry, proof = proven[0]
    manifest = yaml.safe_load(proof.manifest_path.read_text(encoding="utf-8"))
    report = proof.manifest_path.parent / manifest["report"]
    assert report.is_file(), f"the real report channel {report} must exist"

    from atdd.enforce.resolution import resolve_provider

    provider = resolve_provider(
        [
            _REPO_ROOT / ".atdd" / "workspaces",
            _REPO_ROOT / ".atdd" / "extensions",
            _REPO_ROOT / ".atdd",
        ],
        entry["workspace_id"],
        f"^{entry['contract_version']}",
    )
    assert provider.provider_cli_path.is_file(), (
        "the real vendored provider CLI must exist on disk; core locates it and "
        "never imports it"
    )


def test_a_rule_absent_from_the_real_lock_is_refused(resolver, real_lock):
    """No looser match rescues a rule the real lock does not name exactly."""
    declared = {c["convention_id"] for c in real_lock["conventions"]}

    for absent in (
        "coder.definitely.not-a-real-bound-rule",
        # A real convention id with one segment removed — a prefix must not match.
        sorted(declared)[0].rsplit(".", 1)[0],
    ):
        assert absent not in declared, "the premise: this id is not in the lock"
        proof = resolver.proof_for(absent)
        assert proof.discharges is False
        assert proof.basis == "no-lock-entry"


def test_path_b_really_is_a_blocking_gate_in_this_repo():
    """The last leg, read off the real CI workflow rather than assumed.

    ``registry.path_b_is_blocking``'s docstring still says "Today it is advisory,
    so this returns False"; executed against the real workflow it returns True
    (the workflow became blocking in #1428). Measuring it here rather than
    trusting the comment is the point — a stale docstring in this subsystem has
    misled more than one reader.
    """
    from atdd.enforce.registry import path_b_is_blocking

    assert path_b_is_blocking(_REPO_ROOT) is True, (
        "Path B is not blocking in this repository, so no bound realization can "
        "be complete proof here"
    )
