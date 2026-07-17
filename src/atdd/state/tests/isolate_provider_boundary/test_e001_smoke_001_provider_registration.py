# URN: test:isolate-provider-boundary:register-sync-providers:E001-SMOKE-001-provider-registration
# Acceptance: acc:isolate-provider-boundary:E001-SMOKE-001-provider-registration
# WMBT: wmbt:isolate-provider-boundary:E001
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: In a real checkout, the real `atdd state providers` CLI reports ZERO providers by default, discovers a REAL extension package registered through the composition root, and the same checkout's lifecycle gate (`atdd state merge-authority`) passes identically whether the extension is attached or not — proving no lifecycle decision consults the registry. Refs #1400.
"""The registry is empty by default, and lifecycle does not care what is in it (E001-SMOKE-001).

wagon: isolate-provider-boundary | feature: register-sync-providers | phase: SMOKE
WMBT: wmbt:isolate-provider-boundary:E001

The first assertion is the M5 exit criterion in one command: a real checkout, the real CLI, and no
providers — because *empty by default* is what makes core's default configuration the provider-free
one, rather than something an operator has to remember to arrange.

The last assertion is the acceptance's real content. The merge-authority run — the gate that
decides whether a branch may land — is executed twice over the same commit: once with a real
extension registered and once without. The two runs agree, check for check. An extension can be
attached or removed without changing what core decides, which is the whole point of §8.
"""
from __future__ import annotations

import pytest

from ._live import (
    EXTENSION_SPEC,
    atdd_state,
    commit,
    gh_was_invoked,
    install_extension,
    repo_on_bare_remote,
    seed_object,
)


@pytest.mark.smoke
def test_e001_smoke_001_provider_registration(tmp_path) -> None:
    """Empty by default; a real extension is discovered; lifecycle decides the same either way."""
    _remote, repo = repo_on_bare_remote(tmp_path)
    extension = install_extension(tmp_path)

    # Empty by default. Not "empty because this fixture cleared it" — empty because core ships
    # with no providers and that is the configuration the M5 criterion is about.
    default = atdd_state(repo, "providers")
    assert default.returncode == 0, default.stdout + default.stderr
    assert "no SyncProvider is registered" in default.stdout
    assert "provider-free" in default.stdout

    # A REAL extension package, registered through the composition root.
    registered = atdd_state(repo, "providers", "--provider", EXTENSION_SPEC, extension=extension)
    assert registered.returncode == 0, registered.stdout + registered.stderr
    assert "demo" in registered.stdout
    assert "1 provider(s) registered" in registered.stdout

    # Now the acceptance: does the LIFECYCLE gate care? Author a real object, commit it, and run
    # the merge-authority gate twice over the same commit — once with the extension attached.
    uid = seed_object(repo)
    from atdd.state.projection import object_digest
    import yaml

    document = yaml.safe_load(
        (repo / ".atdd" / "state" / "projection" / f"{uid}.yaml").read_text(encoding="utf-8"))
    base = commit(repo, "\n".join([
        "feat: author feature-x",
        "",
        f"ATDD-Object: {uid}",
        f"ATDD-Projection-Digest: {object_digest(document)}",
    ]))
    assert base

    without = atdd_state(repo, "merge-authority", "--actor", "core-lifecycle")
    with_ext = atdd_state(repo, "merge-authority", "--actor", "core-lifecycle",
                          extension=extension)

    assert without.returncode == 0, without.stdout + without.stderr
    assert with_ext.returncode == 0, with_ext.stdout + with_ext.stderr
    assert "merge-authority run PASSED" in without.stdout

    # Check for check, verdict for verdict, the two runs agree. The extension is installed and
    # importable in the second one and it changed nothing, because nothing on the gate's path can
    # see it.
    assert _verdicts(without.stdout) == _verdicts(with_ext.stdout)
    assert len(_verdicts(without.stdout)) == 7

    # And the gate does not even ACCEPT a --provider flag. There is no seam through which a
    # provider could be handed to it — which is a stronger statement than "it ignores one".
    rejected = atdd_state(repo, "merge-authority", "--provider", EXTENSION_SPEC,
                          extension=extension)
    assert rejected.returncode != 0
    assert "unrecognized arguments" in rejected.stderr

    assert gh_was_invoked(repo) == []


def _verdicts(stdout: str) -> list:
    """Every ``[PASS]``/``[FAIL] <check>`` line the merge-authority run reported."""
    return [
        line.strip() for line in stdout.splitlines()
        if line.startswith("[PASS]") or line.startswith("[FAIL]")
    ]
