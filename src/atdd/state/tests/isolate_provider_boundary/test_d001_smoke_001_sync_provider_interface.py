# URN: test:isolate-provider-boundary:define-provider-interface:D001-SMOKE-001-sync-provider-interface
# Acceptance: acc:isolate-provider-boundary:D001-SMOKE-001-sync-provider-interface
# WMBT: wmbt:isolate-provider-boundary:D001
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: In a real checkout of a real bare remote with a real State Store, the real `atdd state mirror` CLI drives a REAL extension package through the seam: a conforming provider's bot-namespaced refs land in external_refs.*, and a rogue provider returning a non-bot-namespaced ref is refused with nothing written. No mocks, no manual patching. Refs #1400.
"""The seam holds against a real extension, driven by the real CLI (D001-SMOKE-001).

wagon: isolate-provider-boundary | feature: define-provider-interface | phase: SMOKE
WMBT: wmbt:isolate-provider-boundary:D001

Everything in this test is the real thing: a real object minted into a real ``state.sqlite`` by the
real CLI, projected to real canonical bytes, and mirrored by a real extension package that lives in
its own directory, is imported off ``PYTHONPATH``, and **imports core nowhere**. Core reaches it
through the composition root — ``--provider atdd_ext_demo:make`` — which means core imports the
*string the operator handed it* and never a provider by name.

Then the same command with the same shape of extension, differing in exactly one respect: it
returns a ref outside the bot namespace. It is refused, and the projection on disk is unchanged.
That is the seam being load-bearing rather than decorative.
"""
from __future__ import annotations

import pytest
import yaml

from ._live import (
    EXTENSION_SPEC,
    ROGUE_EXTENSION_SOURCE,
    atdd_state,
    gh_was_invoked,
    install_extension,
    projection_file,
    repo_on_bare_remote,
    seed_object,
)


@pytest.mark.smoke
def test_d001_smoke_001_sync_provider_interface(tmp_path) -> None:
    """A conforming extension mirrors through external_refs; a rogue one is refused, writing nothing."""
    _remote, repo = repo_on_bare_remote(tmp_path)
    extension = install_extension(tmp_path)
    uid = seed_object(repo)

    before = projection_file(repo, uid).read_bytes()

    mirrored = atdd_state(repo, "mirror", "--provider", EXTENSION_SPEC, extension=extension)

    assert mirrored.returncode == 0, mirrored.stdout + mirrored.stderr
    document = yaml.safe_load(projection_file(repo, uid).read_text(encoding="utf-8"))

    # The provider's refs landed — under external_refs, bot-namespaced, and nowhere else.
    assert document["external_refs"] == {"demo": {"issue_number": "1400"}}
    assert document["phase"] == "INIT"
    assert document["slug"] == "feature-x"

    # A ROGUE extension: same package shape, one difference — its ref is not bot-namespaced.
    rogue_repo = repo
    rogue = install_extension(tmp_path, ROGUE_EXTENSION_SOURCE, name="rogue-ext")
    after_good = projection_file(rogue_repo, uid).read_bytes()

    refused = atdd_state(rogue_repo, "mirror", "--provider", EXTENSION_SPEC, "--strict",
                         extension=rogue)

    assert refused.returncode != 0, "a non-bot-namespaced ref must not reach the projection"
    assert "bot" in refused.stderr or "bot" in refused.stdout

    # Nothing was written. The projection is byte-for-byte what the conforming mirror left.
    assert projection_file(rogue_repo, uid).read_bytes() == after_good

    # And none of it went anywhere near GitHub.
    assert gh_was_invoked(repo) == []
    assert before != after_good, "the conforming mirror did change something (else this proves nothing)"
