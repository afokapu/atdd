# URN: test:govern-projection-fields:define-actor-ownership:D002-SMOKE-001-single-owner-body-rule-computability
# Acceptance: acc:govern-projection-fields:D002-SMOKE-001-single-owner-body-rule-computability
# WMBT: wmbt:govern-projection-fields:D002
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: end-to-end against a real store and real commits: an object minted by the real CLI carries owner_actor in its projection, the real field-writer command accepts the owner's body edit and rejects a second writer's — naming the owner and the conflict-unless-single-owner rule — and the real merge driver names both sides' writers when the body diverges Refs #1400.
"""The owner rides on the object, so the rule is computable live (D002-SMOKE-001).

wagon: govern-projection-fields | feature: define-actor-ownership | phase: SMOKE
WMBT: wmbt:govern-projection-fields:D002

The object is minted by the real CLI into a real ``.atdd/state/state.sqlite`` and projected by
the real projector, so ``owner_actor`` is in the committed bytes because the *system* put it
there — not because a fixture typed it. Then both readers of that field are driven for real:
the field-writer command judges a body edit by who committed it, and the merge driver explains
a divergent body by naming the two people who wrote it.
"""
from __future__ import annotations

import pytest
import yaml

from atdd.state.ownership import RULE_SINGLE_OWNER
from atdd.state.projection import canonical_bytes

from ._live import atdd_state, commit, projection_file, repo_on_bare_remote


@pytest.mark.smoke
def test_d002_smoke_001_single_owner_body_rule_computability(tmp_path) -> None:
    """A real object carries its owner; the real validator and driver both read it."""
    _remote, repo = repo_on_bare_remote(tmp_path)
    assert atdd_state(repo, "init").returncode == 0

    created = atdd_state(repo, "object", "create", "--slug", "feature-x",
                         "--owner", "dev-a", "--body", "the original body")
    assert created.returncode == 0, created.stderr
    uid = created.stdout.strip().split()[0]

    assert atdd_state(repo, "project").returncode == 0
    document = yaml.safe_load(projection_file(repo, uid).read_text(encoding="utf-8"))
    assert document["owner_actor"] == "dev-a", "the projector carries the owner into the bytes"

    base = commit(repo, "feat: mint feature-x")

    # A body edit, committed. The validator's verdict depends on WHO is claimed to have made it.
    edited = {**document, "body": "a rewrite"}
    projection_file(repo, uid).write_bytes(canonical_bytes(edited))
    commit(repo, "feat: rewrite the body")

    owner = atdd_state(repo, "field-writer", "--base", base, "--actor", "dev-a")
    assert owner.returncode == 0, owner.stdout + owner.stderr

    intruder = atdd_state(repo, "field-writer", "--base", base, "--actor", "dev-b")
    assert intruder.returncode == 1
    assert "body" in intruder.stderr
    assert "dev-a" in intruder.stderr, "the report names the owner the rule is computed against"
    assert RULE_SINGLE_OWNER in intruder.stderr

    # And the merge driver, refusing a divergent body, names the writer on each side.
    ours = tmp_path / f"{uid}.yaml"
    theirs = tmp_path / "theirs.yaml"
    base_doc = tmp_path / "base.yaml"
    base_doc.write_bytes(canonical_bytes(document))
    ours.write_bytes(canonical_bytes({**document, "body": "A's rewrite"}))
    theirs.write_bytes(canonical_bytes(
        {**document, "body": "B's rewrite", "owner_actor": "dev-b"}))

    merged = atdd_state(repo, "merge-projection", "--base", str(base_doc),
                        "--ours", str(ours), "--theirs", str(theirs))
    assert merged.returncode == 1
    assert "dev-a" in merged.stderr and "dev-b" in merged.stderr
    assert RULE_SINGLE_OWNER in merged.stderr
