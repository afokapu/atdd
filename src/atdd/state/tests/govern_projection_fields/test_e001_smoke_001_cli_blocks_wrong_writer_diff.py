# URN: test:govern-projection-fields:validate-field-writer:E001-SMOKE-001-cli-blocks-wrong-writer-diff
# Acceptance: acc:govern-projection-fields:E001-SMOKE-001-cli-blocks-wrong-writer-diff
# WMBT: wmbt:govern-projection-fields:E001
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: in a real checkout of a real bare remote, the real `atdd state field-writer` CLI run over a real commit range exits non-zero on a human-authored commit whose projection diff mutates external_refs — its stderr naming the offending field and the legal writer extension-bot — while the same command over a core-lifecycle phase commit exits zero, and the actor is resolved from the commit's own git author identity Refs #1400.
"""The wrong writer is blocked over real commits, by the real CLI (E001-SMOKE-001).

wagon: govern-projection-fields | feature: validate-field-writer | phase: SMOKE
WMBT: wmbt:govern-projection-fields:E001

Real commits, made by real ``git commit`` under real author identities, judged by the real
command over a real commit range. The actor is not a flag somebody passes: it is read off the
commit, which is the only version of this check that cannot be talked around.

The remote is bare — git object storage, no GitHub, no API, no provider — which is the point
rather than a convenience. The rule being enforced is *about* the GitHub mirror, and it is
enforced without GitHub anywhere in the room (I7).
"""
from __future__ import annotations

import pytest

from atdd.state.ownership import WRITER_EXTENSION_BOT
from atdd.state.projection import canonical_bytes

from ._helpers import UID_X, document
from ._live import atdd_state, commit, projection_file, repo_on_bare_remote

HUMAN = "Dev A <dev-a@example.invalid>"
BOT = "github-actions[bot] <41898282+github-actions[bot]@users.noreply.github.com>"


@pytest.mark.smoke
def test_e001_smoke_001_cli_blocks_wrong_writer_diff(tmp_path) -> None:
    """A human's external_refs commit is refused; a core-lifecycle phase commit is admitted."""
    _remote, repo = repo_on_bare_remote(tmp_path)

    seed = document(phase="PLANNED", external_refs={"github": {"issue_number": 1400}})
    projection_file(repo, UID_X).parent.mkdir(parents=True, exist_ok=True)
    projection_file(repo, UID_X).write_bytes(canonical_bytes(seed))
    base = commit(repo, "feat: seed the projection", author=HUMAN)

    # A HUMAN commit that mutates the provider's subtree.
    projection_file(repo, UID_X).write_bytes(
        canonical_bytes({**seed, "external_refs": {"github": {"issue_number": 1401}}}))
    commit(repo, "chore: fix up the issue number by hand", author=HUMAN)

    refused = atdd_state(repo, "field-writer", "--base", base)

    assert refused.returncode != 0, "a wrong-writer diff must not reach main"
    assert "external_refs" in refused.stderr
    assert WRITER_EXTENSION_BOT in refused.stderr
    # The actor came from the COMMIT, not from a flag: the report names the human git recorded.
    assert "dev-a@example.invalid" in refused.stderr

    # The same command over a core-lifecycle phase commit exits zero.
    projection_file(repo, UID_X).write_bytes(canonical_bytes({**seed, "phase": "RED"}))
    phase_commit = commit(repo, "feat: PLANNED->RED\n\nATDD-Object: " + UID_X, author=HUMAN)
    admitted = atdd_state(repo, "field-writer", "--base", base, "--head", phase_commit,
                          "--actor", "core-lifecycle")
    assert admitted.returncode == 0, admitted.stdout + admitted.stderr

    # ...and the bot doing the same thing is refused from the other side of the boundary.
    projection_file(repo, UID_X).write_bytes(canonical_bytes({**seed, "phase": "GREEN"}))
    commit(repo, "chore: mirror says GREEN", author=BOT)
    bot = atdd_state(repo, "field-writer", "--base", base)
    assert bot.returncode != 0
    assert "phase" in bot.stderr
    assert "core-lifecycle" in bot.stderr
