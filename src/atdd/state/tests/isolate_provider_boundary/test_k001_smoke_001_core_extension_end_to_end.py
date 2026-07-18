# URN: test:isolate-provider-boundary:validate-extension-integration:K001-SMOKE-001-core-extension-end-to-end
# Acceptance: acc:isolate-provider-boundary:K001-SMOKE-001-core-extension-end-to-end
# WMBT: wmbt:isolate-provider-boundary:K001
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: A real core checkout on a real bare remote with a REAL extension provider package installed and registered: the core workflow completes and CI merge authority passes WITHOUT consulting the provider; the mirror job runs after merge and applies external_refs.* only, committed by the bot and admitted by the field-writer gate; a mirror that raises still exits 0 and leaves merge authority passing; and removing the extension leaves the core workflow passing unchanged. Refs #1400.
"""Core plus a real extension, end to end, on a bare remote (K001-SMOKE-001).

wagon: isolate-provider-boundary | feature: validate-extension-integration | phase: SMOKE
WMBT: wmbt:isolate-provider-boundary:K001

The whole wagon, driven the way it will actually be used. A real extension package on disk that
never imports ``atdd``; core reaching it through the composition root and never naming it; the real
CLI; a bare remote with no API behind it. Four claims, in the order an operator meets them:

1. The core workflow completes and the merge-authority gate passes **with the extension installed
   and registered** — and the gate never consults it, because it cannot.
2. The mirror job runs **after merge**, and what it writes is ``external_refs.*`` and nothing else.
   It is committed by the **bot**, and the field-writer gate — wagon 4's — admits it. The two halves
   of the boundary agree about who owns what, which is the point of there being one ownership table.
3. A mirror that **raises** exits 0 and leaves merge authority passing. GitHub being down does not
   block a merge.
4. Removing the extension changes nothing. Core does not notice it is gone, which is the strongest
   form of "the extension is presentation-only" — you cannot tell from core's behaviour whether it
   was ever there.
"""
from __future__ import annotations

import pytest
import yaml

from atdd.state.projection import object_digest

from ._live import (
    BROKEN_EXTENSION_SOURCE,
    EXTENSION_SPEC,
    atdd_state,
    commit,
    commit_projection,
    gh_was_invoked,
    git,
    install_extension,
    projection_file,
    repo_on_bare_remote,
    seed_object,
)

BOT = "github-actions[bot] <41898282+github-actions[bot]@users.noreply.github.com>"


@pytest.mark.smoke
def test_k001_smoke_001_core_extension_end_to_end(tmp_path) -> None:
    """The extension mirrors after merge, never blocks it, and removing it changes nothing."""
    remote, repo = repo_on_bare_remote(tmp_path)
    extension = install_extension(tmp_path)

    # (1) The core workflow, with a real extension installed. It completes, and CI passes.
    uid = seed_object(repo, extension=extension)
    base = git(repo, "rev-parse", "HEAD").stdout.strip()
    commit_projection(repo, uid)
    git(repo, "push", "--quiet", "origin", "main")
    merged = git(repo, "rev-parse", "HEAD").stdout.strip()

    gate = atdd_state(repo, "merge-authority", "--base", base, "--actor", "core-lifecycle",
                      extension=extension)
    assert gate.returncode == 0, gate.stdout + gate.stderr
    assert "merge-authority run PASSED" in gate.stdout
    assert "core-no-provider" in gate.stdout

    lifecycle_fields = yaml.safe_load(projection_file(repo, uid).read_text(encoding="utf-8"))
    assert "external_refs" not in lifecycle_fields, (
        "the merge landed WITHOUT the mirror — the mirror runs after merge, not before it (spec §9)"
    )

    # (2) The mirror job runs AFTER merge. It writes external_refs.* and nothing else, as the bot.
    mirrored = atdd_state(repo, "mirror", "--provider", EXTENSION_SPEC, extension=extension)
    assert mirrored.returncode == 0, mirrored.stdout + mirrored.stderr

    after = yaml.safe_load(projection_file(repo, uid).read_text(encoding="utf-8"))
    assert after["external_refs"] == {"demo": {"issue_number": "1400"}}
    for field, value in lifecycle_fields.items():
        assert after[field] == value, f"the mirror wrote the lifecycle field {field!r}"

    # The bot commits its own write — and it commits it like any other projection change: with the
    # trailers that name the object and pin the bytes. The mirror does not get a quiet side door
    # into the history; §5 applies to it too, and the trailer cross-check enforces that it does.
    #
    # Judged against `merged`, the commit the mirror ran *after*: that diff is the mirror's own work
    # and nothing else. Judged against `base` it would also contain the human's authoring commit,
    # and the gate would rightly refuse — a bot cannot be the writer of a diff it did not make. The
    # mirror job runs after merge (spec §9), and this is what "after" means to CI.
    mirror_commit = commit(repo, "\n".join([
        "chore: mirror external refs",
        "",
        f"ATDD-Object: {uid}",
        f"ATDD-Projection-Digest: {object_digest(after)}",
    ]), author=BOT)
    assert mirror_commit
    writer = atdd_state(repo, "field-writer", "--base", merged, extension=extension)
    assert writer.returncode == 0, writer.stdout + writer.stderr
    assert "every projection field was written by its owner" in writer.stdout

    # ...and merge authority still passes over the mirrored projection.
    after_mirror = atdd_state(repo, "merge-authority", "--base", merged, "--actor", BOT,
                              extension=extension)
    assert after_mirror.returncode == 0, after_mirror.stdout + after_mirror.stderr

    # (3) A mirror that RAISES exits 0, and merge authority is untouched.
    broken = install_extension(tmp_path, BROKEN_EXTENSION_SOURCE, name="broken-ext")
    failed = atdd_state(repo, "mirror", "--provider", EXTENSION_SPEC, extension=broken)

    assert failed.returncode == 0, (
        "a failing mirror must NOT return non-zero: a provider outage would block every merge (I7)"
    )
    assert "FAILED demo" in failed.stdout
    assert "may not block a merge" in failed.stdout
    assert yaml.safe_load(projection_file(repo, uid).read_text(encoding="utf-8")) == after, (
        "the failed mirror changed the projection"
    )

    still_mergeable = atdd_state(repo, "merge-authority", "--base", merged, "--actor", BOT,
                                 extension=broken)
    assert still_mergeable.returncode == 0, still_mergeable.stdout + still_mergeable.stderr

    # (4) Remove the extension entirely. Core does not notice.
    without = atdd_state(repo, "merge-authority", "--base", merged, "--actor", BOT)
    assert without.returncode == 0, without.stdout + without.stderr
    assert _verdicts(without.stdout) == _verdicts(still_mergeable.stdout)

    assert atdd_state(repo, "canonicality").returncode == 0
    assert atdd_state(repo, "import-boundary").returncode == 0

    no_providers = atdd_state(repo, "mirror")
    assert no_providers.returncode == 0, "with no extension the mirror is a no-op, not a failure"
    assert "0 external ref(s)" in no_providers.stdout

    # Nothing, anywhere in any of that, reached for GitHub.
    assert gh_was_invoked(repo) == []


def _verdicts(stdout: str) -> list:
    return [
        line.strip() for line in stdout.splitlines()
        if line.startswith("[PASS]") or line.startswith("[FAIL]")
    ]
