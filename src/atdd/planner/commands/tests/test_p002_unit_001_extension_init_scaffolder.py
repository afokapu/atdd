# URN: test:author-atdd-substrate:substrate-spine:P002-UNIT-001-extension-init-scaffolds
# Acceptance: acc:author-atdd-substrate:P002-UNIT-001-extension-init-scaffolds
# WMBT: wmbt:author-atdd-substrate:P002
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""P002-UNIT-001 — `extension init` scaffolds a schema-valid extension package; bad id + overwrite refused."""
from __future__ import annotations

import pytest
import yaml

from atdd.planner.commands.author import AuthorInputError
from atdd.planner.commands.author_init import init_extension_package


def test_extension_init_scaffolds_manifest_and_skeleton(tmp_path):
    pkg = init_extension_package("acme.extension.component-header-validator", root=tmp_path)

    assert pkg == tmp_path / "extensions/acme.extension.component-header-validator"
    manifest = yaml.safe_load((pkg / "atdd.extension.yaml").read_text())
    assert manifest["extension_id"] == "acme.extension.component-header-validator"
    assert manifest["kind"] == "extension"
    # four-layer vocabulary: owns implementations (not validators) + workspaces dep slot
    assert "implementations" in manifest["owns"]
    assert "workspaces" in manifest["depends_on"]
    # canonical folder skeleton
    for sub in ("conventions", "validators", "scopes", "gates", "e2e"):
        assert (pkg / sub).is_dir()


def test_extension_init_refuses_bad_id(tmp_path):
    with pytest.raises(AuthorInputError) as exc:
        init_extension_package("acme.workspace.python-pytest", root=tmp_path)  # wrong scope
    assert exc.value.field == "extension"


def test_extension_init_refuses_overwrite(tmp_path):
    init_extension_package("acme.extension.demo", root=tmp_path)
    with pytest.raises(AuthorInputError) as exc:
        init_extension_package("acme.extension.demo", root=tmp_path)
    assert "exists" in str(exc.value).lower()
