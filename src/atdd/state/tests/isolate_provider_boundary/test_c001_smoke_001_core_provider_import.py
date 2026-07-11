# URN: test:isolate-provider-boundary:enforce-import-boundary:C001-SMOKE-001-core-provider-import
# Acceptance: acc:isolate-provider-boundary:C001-SMOKE-001-core-provider-import
# WMBT: wmbt:isolate-provider-boundary:C001
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: The real `atdd state import-boundary` CLI, run by subprocess in a real checkout against the real shipped package, exits 0 and reports the graph provider-free — and exits non-zero naming the offender and the §8.1 law when pointed at a package whose core imports a provider. No mocks, no manual patching. Refs #1400.
"""The boundary guard is a command CI can run, and it bites (C001-SMOKE-001).

wagon: isolate-provider-boundary | feature: enforce-import-boundary | phase: SMOKE
WMBT: wmbt:isolate-provider-boundary:C001

The real CLI, by subprocess, in a real checkout of a real bare remote — and pointed at the real
shipped ``atdd`` package, not a fixture's idea of one. A guard that exists only as a function some
test calls protects nothing; what protects the branch is a command with an exit code, which is
what is driven here.

Both directions, because a gate only ever seen to pass is a gate nobody knows the shape of: the
same command over a package whose core imports a provider exits non-zero and says why.
"""
from __future__ import annotations

import pytest

from atdd.state import import_boundary

from ._live import atdd_state, gh_was_invoked, repo_on_bare_remote
from ._seam import IMPORTS_PROVIDER, SHELLS_OUT_TO_GH, core_package


@pytest.mark.smoke
def test_c001_smoke_001_core_provider_import(tmp_path) -> None:
    """The shipped package passes the real command; a package with a provider import fails it."""
    _remote, repo = repo_on_bare_remote(tmp_path)

    clean = atdd_state(repo, "import-boundary")

    assert clean.returncode == 0, clean.stdout + clean.stderr
    assert "provider-free" in clean.stdout
    assert "§8.1" in clean.stdout

    # The same command, over a core package that imports a provider and shells out to gh.
    package = core_package(tmp_path / "rogue", {
        "projection": IMPORTS_PROVIDER,
        "evidence": SHELLS_OUT_TO_GH,
    })
    refused = atdd_state(repo, "import-boundary", "--package", str(package))

    assert refused.returncode != 0, "the CLI must fail the run, not merely mention the problem"
    assert "github" in refused.stderr
    assert "projection" in refused.stderr
    assert import_boundary.RULE_GH_SHELL_OUT in refused.stderr
    assert "§8.1" in refused.stderr

    # And the guard never reached for the GitHub CLI to decide any of that.
    assert gh_was_invoked(repo) == []
