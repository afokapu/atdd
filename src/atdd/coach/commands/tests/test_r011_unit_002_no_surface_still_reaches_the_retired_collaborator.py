# URN: test:govern-lifecycle:govern-lifecycle:R011-UNIT-002-no-surface-still-reaches-the-retired-collaborator
# Acceptance: acc:govern-lifecycle:R011-UNIT-002-no-surface-still-reaches-the-retired-collaborator
# WMBT: wmbt:govern-lifecycle:R011
# Phase: RED
# Layer: application
"""R011-UNIT-002 — finish the retirement rather than patch what was reported.

Two dangling reads were REPORTED. Asserting only those two would leave the next
one for the next reader, so this drives the whole public surface and the module's
own text: no method may reach a collaborator the class no longer constructs.
"""
from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from atdd.coach.commands import gate as gate_module
from atdd.coach.commands.gate import ATDDGate


@pytest.mark.coder
def test_no_method_reaches_the_retired_syncer_collaborator():
    """`self.syncer` was removed from __init__ by #1812; nothing may still call it."""
    source = Path(inspect.getfile(gate_module)).read_text(encoding="utf-8")

    assert "self.syncer" not in source, (
        "the syncer attribute is no longer constructed, so any method reaching it "
        "is an AttributeError waiting for its first caller"
    )


@pytest.mark.coder
def test_every_public_method_can_be_invoked_without_raising(tmp_path):
    """The generalisation of the two reported failures.

    Both reported defects were public methods that raised on call. Enumerating
    the surface rather than naming those two is what stops a third from surviving.
    """
    instance = ATDDGate(target_dir=tmp_path)
    raised: dict[str, str] = {}

    for name, method in inspect.getmembers(instance, inspect.ismethod):
        if name.startswith("_"):
            continue
        params = [
            p for p in inspect.signature(method).parameters.values()
            if p.default is inspect.Parameter.empty
        ]
        if params:
            continue  # needs arguments; not a zero-arg entry point
        try:
            method()
        except Exception as exc:  # noqa: BLE001 — the assertion is that none escape
            raised[name] = f"{type(exc).__name__}: {exc}"

    assert not raised, f"public entry points raised: {raised}"


@pytest.mark.coder
def test_the_documented_return_contract_matches_what_the_code_can_produce(tmp_path):
    """`verify` promised "1 if no synced files found"; nothing can return 1 now."""
    doc = inspect.getdoc(ATDDGate.verify) or ""

    assert "synced files" not in doc, (
        "the docstring still describes the retired projection's return branch, "
        "sending a reader to look for code that no longer exists"
    )
    assert ATDDGate(target_dir=tmp_path).verify() == 0
