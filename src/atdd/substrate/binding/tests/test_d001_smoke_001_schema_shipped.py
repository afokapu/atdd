# URN: test:bind-substrate-runtime:substrate-binding:D001-SMOKE-001-schema-shipped
# Acceptance: acc:bind-substrate-runtime:D001-SMOKE-001-schema-shipped
# WMBT: wmbt:bind-substrate-runtime:D001
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""D001-SMOKE-001 — the binding-lock schema ships as package data and resolves from
the installed atdd package (no repo checkout); a real binding plan built by
build_binding_plan validates against it, importing no implementation code."""
from __future__ import annotations

from pathlib import Path

import pytest

import atdd
from atdd.substrate.binding import plan as plan_mod
from atdd.substrate.binding import schemas
from atdd.substrate.binding.tests.conftest import install_extension, install_provider


@pytest.mark.smoke
def test_schema_ships_and_real_plan_validates(tmp_path: Path) -> None:
    # The schema resolves package-relatively from the installed atdd package.
    schema_path = schemas._schema_dir() / schemas.BINDING_LOCK_SCHEMA
    assert schema_path == Path(atdd.__file__).resolve().parent / "planner" / "schemas" / "binding-lock.schema.json"
    assert schema_path.exists()
    assert schemas.load_binding_lock_schema()["title"] == "ATDD Binding Lock Schema"

    # A real plan built from a real installed substrate validates against it.
    install_provider(tmp_path)
    install_extension(tmp_path, "acme.extension.demo", convention="demo.gate")
    plan = plan_mod.build_binding_plan(tmp_path)
    schemas.validate_binding_lock(plan)  # would raise BindingSchemaError on drift
    assert plan["substrate_lock_digest"].startswith("sha256:")
