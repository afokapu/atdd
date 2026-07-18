# URN: test:govern-lifecycle:ship-package-data-and-consumer-ci:C008-SMOKE-001-repaired-gate-executes-against-a-real-wheel
# Acceptance: acc:govern-lifecycle:C008-SMOKE-001-repaired-gate-executes-against-a-real-wheel
# WMBT: wmbt:govern-lifecycle:C008
# Phase: SMOKE
# Layer: backend.smoke
# Assertion: behavioral
"""C008-SMOKE-001 — the repaired gate EXECUTES against a real wheel.

Real infra: a wheel built from the checkout and `pip install`ed into a freshly
created virtualenv, then the SHIPPED copy of `test_wheel_completeness` run by pytest
with the toolkit checkout as the working directory. That is the topology the
`validate-consumer` CI job creates, and the only one in which the gate has anything
to say.

Why this needs its own SMOKE and is not covered by the C008 units: the units call the
gate's internals directly (`evaluate_wheel_completeness(...)`), so they prove the
LOGIC is right. They cannot prove that pytest, running the real module in a real
environment, actually reaches that logic — and for the whole life of #451 it did not.
The gate skipped on editable install (how CI runs it) and skipped again from a wheel
(its `__file__` walk found no checkout). Every assertion inside it was correct and
none of them ever ran.

So the assertion here is deliberately two-part: it must PASS, and it must not have
SKIPPED. A green skip is exactly what this issue exists to abolish.
"""
from __future__ import annotations

import subprocess

import pytest

from ._wheel_harness import repo_root
from .test_c009_smoke_001_consumer_sweep_collects_with_zero_errors import (
    _clean_env,
    _consumer_env,
)

# `platform` marks this a TOOLKIT-SELF test: it needs the toolkit checkout (and a
# wheel built from it), which a consumer repo does not have. `atdd validate <phase>`
# adds `-m "not platform"` outside the source repo (E025), so this is deselected there
# and runs here.
pytestmark = [pytest.mark.coach, pytest.mark.platform]


@pytest.mark.smoke
def test_c008_smoke_001_repaired_gate_executes_against_a_real_wheel():
    python, pkg_dir, _ = _consumer_env()

    result = subprocess.run(
        [str(python), "-m", "pytest",
         str(pkg_dir / "coach" / "validators" / "test_wheel_completeness.py"),
         "-q", "-p", "no:cacheprovider", "-rs"],
        capture_output=True, text=True, cwd=repo_root(), env=_clean_env(),
    )
    output = result.stdout + result.stderr

    assert result.returncode == 0, (
        f"the wheel-completeness gate FAILS against the installed wheel — a file the "
        f"source tree ships is absent from the package:\n{output[-3000:]}"
    )
    assert " passed" in output, (
        f"the gate did not execute a single assertion against a real wheel — it "
        f"skipped. That is the #451 defect verbatim: a gate that skips in every "
        f"environment it is ever run in has never enforced anything.\n{output[-2000:]}"
    )
