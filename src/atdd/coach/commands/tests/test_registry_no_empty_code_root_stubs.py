"""Regression: the registry builder must not stub empty code-root registries.

Under the extension-first model, runtime/tech registries (Supabase functions,
the root atdd/tester tests mirror) are extension-domain, not core roots. The
builder must not stamp `functions: []` / `tests: []` placeholders into a repo
that ships none — and it must clean up a pre-existing empty stub.
"""
from __future__ import annotations

from atdd.coach.commands.registry import RegistryUpdater


def test_build_tester_does_not_create_empty_root_stub(tmp_path):
    RegistryUpdater(tmp_path).build_tester(mode="apply")
    assert not (tmp_path / "atdd").exists(), "build_tester stamped an empty root atdd/ registry"


def test_build_supabase_does_not_create_empty_stub(tmp_path):
    RegistryUpdater(tmp_path).build_supabase(mode="apply")
    assert not (tmp_path / "supabase").exists(), "build_supabase stamped an empty supabase/ registry"


def test_build_tester_removes_pre_existing_empty_stub(tmp_path):
    stub = tmp_path / "atdd" / "tester" / "_tests.yaml"
    stub.parent.mkdir(parents=True)
    stub.write_text("tests: []\n")
    RegistryUpdater(tmp_path).build_tester(mode="apply")
    assert not stub.exists()
    assert not (tmp_path / "atdd").exists(), "empty stub dir was not cleaned up"


def test_build_does_not_nuke_a_nonempty_registry(tmp_path):
    # no over-reach: an existing NON-empty registry must be preserved, not removed.
    reg = tmp_path / "supabase" / "_functions.yaml"
    reg.parent.mkdir(parents=True)
    reg.write_text("functions:\n  - id: validate-x\n")
    RegistryUpdater(tmp_path).build_supabase(mode="apply")
    assert reg.exists(), "guard removed a non-empty registry"
