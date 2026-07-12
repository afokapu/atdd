# URN: test:enforce-binding-plan:run-binding-plan:E003-SMOKE-001-run-on-commit
# Acceptance: acc:enforce-binding-plan:E003-SMOKE-001-run-on-commit
# WMBT: wmbt:enforce-binding-plan:E003
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""E003-SMOKE-001 — the binding-plan scan runs on commit and gates it (V3).

The commit hook / CI job invokes the same ``atdd enforce`` gating primitive an
operator runs; its exit code gates the commit/build. Two edge cases from the
hook contract: the scan **no-ops cleanly (exit 0) when there are no bound
conventions**, and it **honors ``CI=true``**.

This drives the gating primitive the hook calls (the real entry point), in a
checkout with no ``.atdd/binding.lock.yaml`` (no bound conventions) and with a
print() in a non-exempt path. RED reason: the ``atdd enforce`` verb is absent,
so the no-bound-rules no-op cannot return 0 (argparse exits 2).
"""
from __future__ import annotations

import pytest

from .conftest import VERB_ABSENT

pytestmark = pytest.mark.smoke


def test_e003_smoke_001_no_op_clean_when_no_bound_conventions(run_enforce, tmp_path) -> None:
    # A checkout with no .atdd/binding.lock.yaml at all: nothing is bound.
    proj = tmp_path / "no_bindings"
    (proj / "src").mkdir(parents=True, exist_ok=True)
    (proj / "src" / "app.py").write_text("def f():\n    return 1\n", encoding="utf-8")

    proc = run_enforce([], cwd=proj, extra_env={"CI": "true"})
    combined = proc.stdout + proc.stderr

    assert VERB_ABSENT not in combined, "atdd enforce is not wired as a command"
    # The hook must no-op cleanly (gate green) when there are no bound rules,
    # honoring CI=true — otherwise every commit in a not-yet-bound repo breaks.
    assert proc.returncode == 0, (
        f"no-bound-rules scan exited {proc.returncode}, expected a clean 0 no-op:\n{combined}"
    )


def test_e003_smoke_001_dirty_non_exempt_path_is_gated(run_enforce, tmp_path) -> None:
    # A print() introduced into a non-exempt production path must red the gate
    # the commit hook / CI job evaluates (non-zero exit blocks the commit/build).
    proj = tmp_path / "dirty_commit"
    pkg = proj / "src" / "service"
    pkg.mkdir(parents=True, exist_ok=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "worker.py").write_text(
        "def run(job):\n    print(job)  # non-exempt production print\n    return job\n",
        encoding="utf-8",
    )

    proc = run_enforce([], cwd=proj, extra_env={"CI": "true"})
    combined = proc.stdout + proc.stderr

    assert VERB_ABSENT not in combined, "atdd enforce is not wired as a command"
    assert proc.returncode != 0, (
        "a print() in a non-exempt production path must gate the commit/build "
        f"(non-zero exit); got {proc.returncode}:\n{combined}"
    )
