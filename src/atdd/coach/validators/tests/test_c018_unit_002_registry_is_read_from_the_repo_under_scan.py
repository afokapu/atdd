# URN: test:govern-lifecycle:bind-issue-train:C018-UNIT-002-registry-is-read-from-the-repo-under-scan
# Acceptance: acc:govern-lifecycle:C018-UNIT-002-registry-is-read-from-the-repo-under-scan
# WMBT: wmbt:govern-lifecycle:C018
# Phase: GREEN
# Layer: domain
# Runtime: python
# Assertion: behavioral
# Purpose: Resolution reads the registry of the repository under scan, so a consumer repository is held to its own trains and atdd's ids do not resolve there.
"""GREEN test for acc:govern-lifecycle:C018-UNIT-002-registry-is-read-from-the-repo-under-scan.

wagon: govern-lifecycle | feature: bind-issue-train | WMBT: wmbt:govern-lifecycle:C018

THE CONSUMER-NEUTRALITY ACCEPTANCE. A check that passes only because it runs
inside atdd is the defect, not the evidence — and the repo already carries a live
example of the failure mode: ``.atdd/config.yaml :: interlocking_layout`` points
the runtime-interlocking detector at atdd's own
``src/atdd/runtime/interlocking/*.py`` paths, so that detector works where it was
written and nowhere else.

The fixture here is a repository that is NOT atdd: wagon ``freight-yard``,
subjects ``rolling-stock`` and ``yard-ops``, train ids that appear nowhere in
atdd's ``plan/_trains.yaml``, and no layout override of any kind. Its own trains
must resolve; a REAL atdd train id must not.
"""
from __future__ import annotations

import pytest

from atdd.coach.validators.issue_train_binding_scanner import scan_train_references
from atdd.planner.commands.train_binding import (
    interlocking_index, plan_is_available, registered_trains, resolve_train,
    train_aliases,
)

from ._bind_issue_train_helpers import (
    ATDD_TRAIN_ID,
    CONSUMER_INTERLOCKING,
    CONSUMER_TRAIN,
    CONSUMER_TRAIN_LEGACY,
    CONSUMER_TRAIN_UNROUTED,
    control_root,
    issue_record,
    write_consumer_plan_tree,
)


@pytest.fixture()
def consumer_repo(tmp_path):
    root = control_root(tmp_path)
    write_consumer_plan_tree(root)
    return root


def test_the_consumer_repos_own_train_resolves(consumer_repo) -> None:
    verdict = resolve_train(CONSUMER_TRAIN, consumer_repo)

    assert verdict.resolved, (
        f"a train the CONSUMER repo registers did not resolve: {verdict.detail}"
    )
    assert verdict.train_id == CONSUMER_TRAIN
    assert "plan/_trains.yaml" in verdict.detail, (
        f"the verdict does not name the registry it read: {verdict.detail!r}"
    )


def test_the_consumer_repos_own_alias_resolves_to_its_own_canonical(consumer_repo) -> None:
    """The alias map is the consumer's, spelled the consumer's way."""
    assert train_aliases(consumer_repo) == {CONSUMER_TRAIN_LEGACY: CONSUMER_TRAIN}

    verdict = resolve_train(CONSUMER_TRAIN_LEGACY, consumer_repo)

    assert verdict.resolved
    assert verdict.train_id == CONSUMER_TRAIN


def test_an_atdd_train_id_does_not_resolve_in_the_consumer_repo(consumer_repo) -> None:
    """The discriminator. If atdd's own registry had leaked in, this resolves.

    ``ATDD_TRAIN_ID`` is a REAL entry in atdd's ``plan/_trains.yaml`` — 56 live
    work items name it — so a resolver reading the toolkit's checkout instead of
    the repo under scan would pass this by accident.
    """
    verdict = resolve_train(ATDD_TRAIN_ID, consumer_repo)

    assert not verdict.resolved, (
        f"an atdd train id resolved inside a repository that does not declare it "
        f"({verdict.detail}) — atdd's registry leaked into the lookup"
    )
    assert CONSUMER_TRAIN in verdict.detail, (
        "the violation lists candidates from some registry other than the "
        f"consumer's: {verdict.detail!r}"
    )


def test_the_registry_read_contains_only_the_consumers_trains(consumer_repo) -> None:
    """No atdd train id may appear in what the reader returns."""
    found = registered_trains(consumer_repo)

    assert set(found) == {CONSUMER_TRAIN, CONSUMER_TRAIN_UNROUTED}, (
        f"the registry read returned trains the consumer never declared: {sorted(found)}"
    )


def test_interlocking_coverage_is_read_from_the_consumers_own_home(consumer_repo) -> None:
    """The second-order lookup is rooted on the consumer too, not on atdd."""
    index = interlocking_index(consumer_repo)

    assert index, "the consumer's own interlocking home was not read at all"
    assert all(
        CONSUMER_INTERLOCKING in ids for ids in index.values()
    ), f"the index carries interlockings the consumer never declared: {index}"

    verdict = resolve_train(CONSUMER_TRAIN, consumer_repo)
    assert verdict.interlockings == [CONSUMER_INTERLOCKING], (
        f"the consumer's interlocking does not cover the train it routes through: "
        f"{verdict.interlockings}"
    )


def test_a_repo_with_no_plan_tree_has_nothing_to_resolve_against(tmp_path) -> None:
    """Absence of a graph is not a violation of it.

    A hermetic caller minting into a bare directory never had a registry. Failing
    it for that would be the guard misfiring rather than working.
    """
    bare = control_root(tmp_path / "bare")

    assert not plan_is_available(bare)
    assert registered_trains(bare) == {}
    assert scan_train_references(
        [issue_record(1, "train:anything:at-all")], plan_root=bare
    ) == [], "a repo with no plan/ tree was reported as being in violation"


def test_a_consumer_repo_declaring_no_interlockings_is_not_reported(tmp_path) -> None:
    """A repo that has not adopted interlockings has a posture, not a defect."""
    root = control_root(tmp_path / "no-interlockings")
    write_consumer_plan_tree(root, with_interlocking=False)

    violations = scan_train_references(
        [issue_record(1, CONSUMER_TRAIN), issue_record(2, CONSUMER_TRAIN_UNROUTED)],
        plan_root=root,
    )

    assert violations == [], (
        "a repository declaring no interlockings at all was reported per-issue: "
        f"{[v.detail for v in violations]}"
    )


def test_the_resolver_names_no_atdd_specific_path() -> None:
    """Anchor guard: the primitive must not hard-code the toolkit's own layout.

    The concrete regression this prevents is a second ``interlocking_layout``: a
    detector whose paths are atdd's, which therefore reports nothing anywhere
    else. Any such literal in the resolution primitive would be one.

    Scanned over the STRING LITERALS AND ATTRIBUTE NAMES the module actually
    executes, not over its text — the docstrings name the anti-pattern on
    purpose, and a prose warning must not read as the violation it warns about.
    """
    import ast
    from pathlib import Path

    import atdd.planner.commands.train_binding as train_binding

    tree = ast.parse(Path(train_binding.__file__).read_text(encoding="utf-8"))
    executed = {
        node.value for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    } - {
        # Docstrings are the module's prose, not its behaviour.
        ast.get_docstring(node) for node in ast.walk(tree)
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef))
    }

    offenders = sorted(
        literal for literal in executed
        if any(marker in literal for marker in ("src/atdd", "atdd/runtime", "interlocking_layout"))
    )
    assert not offenders, (
        f"the resolution primitive executes literals naming atdd's own layout "
        f"({offenders}), which would bind it to this repository — exactly the "
        f"interlocking_layout trap the brief names"
    )
