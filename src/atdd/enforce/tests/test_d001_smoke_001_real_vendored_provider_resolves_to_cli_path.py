# URN: test:govern-providers:D001-SMOKE-001-real-vendored-provider-resolves-to-cli-path
# Acceptance: acc:govern-providers:D001-SMOKE-001-real-vendored-provider-resolves-to-cli-path
# WMBT: wmbt:govern-providers:D001
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""SMOKE Test for acc:govern-providers:D001-SMOKE-001-real-vendored-provider-resolves-to-cli-path.

Over the toolkit's own real vendored substrate (no synthetic fixture), the
python-pytest workspace provider resolves to an on-disk ``cli/scan.py`` — the live
subprocess boundary the enforce runner would shell out to.
"""
from __future__ import annotations

from atdd.coach.utils.repo import find_repo_root
from atdd.enforce.resolution import ResolvedProvider, resolve_provider
from atdd.enforce.runner import _candidate_roots, resolve_substrate_home


def test_real_vendored_provider_resolves_to_cli_path() -> None:
    repo_root = find_repo_root()
    substrate_home = resolve_substrate_home(repo_root)
    candidate_roots = _candidate_roots(substrate_home)

    resolved = resolve_provider(candidate_roots, "atdd.workspace.python-pytest", "^1.0.0")

    assert isinstance(resolved, ResolvedProvider)
    assert resolved.provider_cli_path.is_file()
    assert resolved.provider_cli_path.name == "scan.py"
