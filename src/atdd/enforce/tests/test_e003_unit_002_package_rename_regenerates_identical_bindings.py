# URN: test:govern-providers:E003-UNIT-002-package-rename-regenerates-identical-bindings
# Acceptance: acc:govern-providers:E003-UNIT-002-package-rename-regenerates-identical-bindings
# WMBT: wmbt:govern-providers:E003
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""GREEN Test for acc:govern-providers:E003-UNIT-002-package-rename-regenerates-identical-bindings.

Two substrates identical in every way except the extension PACKAGE id produce
identical convention bindings. So the persona-aware ID grammar rename (#1343/#1344)
is a lock REGENERATION — re-run the compose and the bindings are unchanged — not a
rule MIGRATION touching every convention entry.
"""
from __future__ import annotations

from pathlib import Path

from atdd.substrate.binding.plan import build_binding_plan

from .conftest import install_extension_impl, install_provider


def _substrate(root: Path, ext_id: str) -> None:
    install_provider(root, contract_version="1.0.0")
    install_extension_impl(
        root,
        ext_id=ext_id,
        convention="coder.demo.rule",
        implementation_id="coder.demo.rule",
    )


def test_package_rename_regenerates_identical_bindings(tmp_path: Path) -> None:
    before = tmp_path / "before"
    after = tmp_path / "after"
    before.mkdir()
    after.mkdir()

    _substrate(before, "atdd.extension.coder")
    _substrate(after, "atdd.extension.coder-persona")

    plan_before = build_binding_plan(before)
    plan_after = build_binding_plan(after)

    # The rename never reaches the lock: the convention bindings are identical.
    assert plan_before["conventions"] == plan_after["conventions"]
