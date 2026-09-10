# URN: test:govern-lifecycle:train-identity-resolves-across-vocabularies:E073-UNIT-002-shipped-defaults-name-declared-trains
# Acceptance: acc:govern-lifecycle:E073-UNIT-002-shipped-defaults-name-declared-trains
# WMBT: wmbt:govern-lifecycle:E073
# Phase: GREEN
# Layer: backend.unit
"""E073-UNIT-002 — every train identity the toolkit emits by DEFAULT resolves
against this repository's own registry (#1890).

This is the guard that would have caught the root cause. `atdd author issue`
defaulted its train to `0003-author-substrate`, retired by the #1421 migration, so
every issue authored without an explicit `--train` inherited an identity the
PLANNED gate refuses. The measurement that found it: live issues reference that id
8 times and it resolves against nothing.

Run against the real `plan/`, not a fixture. A fixture registry would have agreed
with a wrong default.
"""
from __future__ import annotations

import pathlib

import pytest
import yaml

from atdd.coach.commands.issue import IssueManager
from atdd.coach.utils.train_identity import check_train_id

pytestmark = [pytest.mark.platform]

REPO_ROOT = pathlib.Path(__file__).resolve().parents[5]
PLAN = REPO_ROOT / "plan"


@pytest.fixture(scope="module")
def declared() -> set:
    ids = IssueManager._registered_train_ids(PLAN)
    assert ids, f"no trains declared under {PLAN} — the guard would pass vacuously"
    return ids


def test_the_authored_issue_default_train_resolves(declared) -> None:
    from atdd.planner.commands import author_issue

    source = pathlib.Path(author_issue.__file__).read_text(encoding="utf-8")
    line = next(ln for ln in source.splitlines() if 'spec.get("train")' in ln)
    default = line.split('or "', 1)[1].split('"', 1)[0]

    verdict = check_train_id(default, declared)
    assert verdict.resolves, (
        f"`atdd author issue` defaults its train to {default!r}, which "
        f"{verdict.detail.splitlines()[0]}\n"
        "Every issue authored without an explicit --train inherits it, and the "
        "PLANNED gate then refuses the issue."
    )
    assert not verdict.legacy_format, (
        f"the default {default!r} is a legacy spelling; a shipped default should "
        "name the canonical identity so new data does not extend the migration."
    )


def test_no_sidecar_file_is_mistaken_for_a_train(declared) -> None:
    """`_aliases.yaml` is the migration map and `_interlockings.yaml` the
    interlocking registry. Globbing them in made `--train _aliases` resolve, and
    the PLANNED gate accept it — a false ACCEPT in a registration gate."""
    for sidecar in ("_aliases", "_interlockings"):
        assert sidecar not in declared, (
            f"{sidecar} is a sidecar under plan/_trains/, not a train, but the "
            "registry reader admits it as one."
        )


def test_every_alias_target_is_itself_declared(declared) -> None:
    """A migration map pointing at an undeclared successor sends the operator
    from one dangling id to another."""
    alias_file = PLAN / "_trains" / "_aliases.yaml"
    if not alias_file.exists():
        pytest.skip("no alias map in this checkout")
    aliases = (yaml.safe_load(alias_file.read_text(encoding="utf-8")) or {}).get("aliases") or {}

    dangling = {
        legacy: target
        for legacy, target in aliases.items()
        if not check_train_id(f"train:{str(target).replace('/', ':')}", declared).resolves
    }
    assert not dangling, (
        "the alias map points at trains that are not declared:\n  "
        + "\n  ".join(f"{k} -> {v}" for k, v in sorted(dangling.items()))
    )
