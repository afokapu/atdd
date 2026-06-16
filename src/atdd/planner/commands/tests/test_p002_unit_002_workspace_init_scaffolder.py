# URN: test:author-atdd-substrate:substrate-spine:P002-UNIT-002-workspace-init-scaffolds
# Acceptance: acc:author-atdd-substrate:P002-UNIT-002-workspace-init-scaffolds
# WMBT: wmbt:author-atdd-substrate:P002
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""P002-UNIT-002 — `workspace init` scaffolds a provider package with a contract_version; bad scope + overwrite refused."""
from __future__ import annotations

import pytest
import yaml

from atdd.planner.commands.author import AuthorInputError
from atdd.planner.commands.author_init import init_workspace_package


def test_workspace_init_scaffolds_provider_with_contract(tmp_path):
    pkg = init_workspace_package("acme.workspace.python-pytest", root=tmp_path)

    assert pkg == tmp_path / "workspaces/acme.workspace.python-pytest"
    manifest = yaml.safe_load((pkg / "atdd.workspace.yaml").read_text())
    assert manifest["workspace_id"] == "acme.workspace.python-pytest"
    assert manifest["kind"] == "workspace"
    # the provider<->implementation seam: an explicit, versioned contract
    assert manifest["contract_version"] == "1.0.0"
    assert manifest["discovers"]["requires_contract"] == "^1.0.0"
    # runtime skeleton (no conventions/scopes/gates — provider owns runtime only)
    for sub in ("runtime", "adapter", "conformance"):
        assert (pkg / sub).is_dir()
    assert not (pkg / "conventions").exists()


def test_workspace_init_refuses_extension_scope(tmp_path):
    with pytest.raises(AuthorInputError) as exc:
        init_workspace_package("acme.extension.python-pytest", root=tmp_path)
    assert exc.value.field == "workspace"


def test_workspace_init_refuses_overwrite(tmp_path):
    init_workspace_package("acme.workspace.demo", root=tmp_path)
    with pytest.raises(AuthorInputError) as exc:
        init_workspace_package("acme.workspace.demo", root=tmp_path)
    assert "exists" in str(exc.value).lower()
