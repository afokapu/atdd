# URN: test:govern-lifecycle:govern-lifecycle:P002-UNIT-001
# Acceptance: acc:govern-lifecycle:P002-UNIT-001-the-source-bridge-still-wins-in-the-toolkit-checkout
# WMBT: wmbt:govern-lifecycle:P002
# Phase: RED
# Layer: backend.unit
# Assertion: behavioral

"""P002-UNIT-001 — inside the toolkit checkout the gates keep testing the working tree.

The source bridge (#928 Gap 4 Item 3) puts the WORKING TREE on the import path, and
that is what the gates must test. Routing them through the `atdd` console script
would break exactly that: its shebang carries `-E`, which discards PYTHONPATH, so
the version gate would silently begin judging the installed wheel instead of the
code being pushed — a worse defect than the one #1875 fixes, and a silent one.

So the ambient interpreter must win here, and the console script must not be
consulted at all. Also pinned: the block is duplicated across the carrier hooks
(they are standalone scripts with no shared-library mechanism, as the bridge and
the emergency bypass already are), so the copies are asserted byte-identical —
a fix applied to one and forgotten in the other fails here rather than in a
consumer's push."""

from __future__ import annotations

import subprocess

import pytest

from atdd.coach.templates.hooks.tests._p002_interpreter_harness import (
    CARRIERS,
    _block,
    _fake_atdd,
    _resolve,
    _toolkit_checkout,
)

pytestmark = [pytest.mark.coach]


@pytest.mark.parametrize("hook", CARRIERS)
def test_p002_unit_001_the_source_bridge_still_wins(hook, tmp_path):
    """In the toolkit checkout the gates must keep testing the working tree."""
    decoy = tmp_path / "decoy"
    decoy.mkdir()
    (decoy / "python-decoy").write_text("")
    (decoy / "python-decoy").chmod(0o755)
    path_dir = _fake_atdd(tmp_path, str(decoy / "python-decoy"))

    chosen = _resolve(hook, repo_root=_toolkit_checkout(tmp_path),
                      path_dir=path_dir, tmp_path=tmp_path)

    assert chosen == "python3", (
        f"{hook} resolved {chosen!r} while the source bridge was active. The bridge "
        "put the WORKING TREE on the import path; the console script's entry point "
        "carries -E and discards it, so this would silently gate the installed "
        "wheel instead of the code being pushed"
    )



def test_p002_unit_001_every_carrier_holds_the_identical_block():
    """The block is duplicated across hooks; prove the copies cannot drift.

    These templates are standalone scripts with no shared-library mechanism — the
    source bridge and the emergency bypass are already copied between them the same
    way. Duplication that cannot be removed can at least be made verifiable, so a
    fix applied to one hook and forgotten in the other fails here rather than in a
    consumer's push six months later.
    """
    blocks = {hook: _block(hook) for hook in CARRIERS}
    first, *rest = blocks.items()
    for hook, block in rest:
        assert block == first[1], (
            f"the interpreter-resolution block in {hook} has drifted from "
            f"{first[0]}; they must stay byte-identical"
        )
