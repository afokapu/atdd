"""The validator/family implementation contract (atdd.core.implementation-schema):
validate_implementation_manifest enforces the executable-validator shape, the
generator scaffolds it by construction, and validate_package enforces it end-to-end."""
from __future__ import annotations

import yaml
import pytest

from atdd.planner.commands.author import AuthorInputError
from atdd.planner.commands.author_init import init_implementation_package
from atdd.planner.commands.author_manifest import validate_implementation_manifest
from atdd.planner.commands.compose import CompositionError, validate_package

_BASE = {
    "kind": "implementation",
    "implementation_id": "coder.x.family_detector",
    "targets_workspace": "acme.workspace.runtime",
    "contract_version": "1.1.0",
    "entrypoint": "src/detect.mjs",
    "report": "src/detect.mjs",
}


def _m(**over):
    d = dict(_BASE)
    d.update(over)
    return d


def test_accepts_v11_family_manifest():
    validate_implementation_manifest(_m(subtype="validator",
                                        emits_rule_ids=["coder.x.a", "coder.x.b"],
                                        realizes_convention="coder.x.a"))


def test_accepts_v10_realizes_only_manifest():
    # v1.0 back-compat: rule binding via realizes_convention, no emits_rule_ids.
    validate_implementation_manifest(_m(realizes_convention="coder.x.a"))


def _drop_rule_binding(m):
    m.pop("emits_rule_ids", None)
    m.pop("realizes_convention", None)


@pytest.mark.parametrize("mutate,field", [
    (lambda m: m.__setitem__("entrypoint", ""), "entrypoint"),
    (lambda m: m.__setitem__("report", ""), "report"),
    (_drop_rule_binding, "emits_rule_ids"),
    (lambda m: m.__setitem__("realizes_convention", "coder.x.zzz"), "realizes_convention"),
    (lambda m: m.__setitem__("subtype", "gate"), "subtype"),
])
def test_rejects_noncompliant(mutate, field):
    m = _m(emits_rule_ids=["coder.x.a"])  # a valid rule binding unless mutated away
    mutate(m)
    with pytest.raises(AuthorInputError) as ei:
        validate_implementation_manifest(m)
    assert getattr(ei.value, "field", None) == field


def test_generator_is_compliant_by_construction(tmp_path):
    pkg = init_implementation_package(
        "demo_family_detector", targets_workspace="acme.workspace.runtime",
        emits_rule_ids=["coder.demo.a", "coder.demo.b"], root=tmp_path)
    manifest = yaml.safe_load((pkg / "atdd.implementation.yaml").read_text())
    validate_implementation_manifest(manifest)  # must not raise
    assert manifest["subtype"] == "validator"
    assert manifest["emits_rule_ids"] == ["coder.demo.a", "coder.demo.b"]
    assert (pkg / "src" / "detect.mjs").is_file()


def test_generator_refuses_no_emits(tmp_path):
    with pytest.raises(AuthorInputError):
        init_implementation_package("x", targets_workspace="acme.workspace.runtime",
                                    emits_rule_ids=[], root=tmp_path)


def test_validate_package_enforces_impl_contract(tmp_path):
    # Minimal workspace package with one BROKEN implementation manifest.
    ws = tmp_path / "acme.workspace.runtime"
    (ws).mkdir()
    (ws / "atdd.workspace.yaml").write_text(yaml.safe_dump({
        "schema_version": "1.0.0", "workspace_id": "acme.workspace.runtime",
        "version": "0.1.0", "kind": "workspace", "contract_version": "1.0.0",
        "runtime": {"language": "typescript", "runner": "node", "package_manager": "pnpm", "command": "node"},
        "shared_runtime": {"files": []},
        "discovers": {"implementations": ["**/atdd.implementation.yaml"], "requires_contract": "^1.0.0"},
        "conformance": {"suite": "conformance/"}, "governed_by_conventions": [],
    }))
    impl = ws / "implementations" / "broken"
    impl.mkdir(parents=True)
    (impl / "atdd.implementation.yaml").write_text(yaml.safe_dump({
        "kind": "implementation", "implementation_id": "broken",
        "targets_workspace": "acme.workspace.runtime", "contract_version": "1.0.0",
        # missing entrypoint/report/rule-binding
    }))
    with pytest.raises(CompositionError):
        validate_package(ws)
