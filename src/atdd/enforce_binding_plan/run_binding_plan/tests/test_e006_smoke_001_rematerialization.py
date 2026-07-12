# URN: test:enforce-binding-plan:run-binding-plan:E006-SMOKE-001-rematerialization
# Acceptance: acc:enforce-binding-plan:E006-SMOKE-001-rematerialization
# WMBT: wmbt:enforce-binding-plan:E006
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""E006-SMOKE-001 — the vendor-vs-lock re-materialization decision is enforced (V6).

D-5's default is (b): the vendored ``.atdd/{extensions,workspaces}`` trees are
tracked, load-bearing code, guarded by a digest check against
``substrate.lock.yaml``. The runner must expose an automated check that the
vendored trees are present and digest-matched.

This drives the runner's substrate-verification capability against a fixture
whose vendored copy has been tampered with (digest mismatch): the check must
fail. RED reason: the ``atdd enforce`` verb is absent (no verification capability
is shipped yet), so argparse rejects it. When the digest guard ships, a tampered
vendored copy reds the check and an intact one passes.
"""
from __future__ import annotations

import hashlib

import pytest

from .conftest import VERB_ABSENT

pytestmark = pytest.mark.smoke


def _digest(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _vendored_substrate(root, *, detector_body: str) -> None:
    """Lay down a minimal vendored tree + substrate.lock.yaml recording its digest."""
    art_dir = root / ".atdd" / "workspaces" / "atdd.workspace.python-pytest" / "1.0.0"
    art_dir.mkdir(parents=True, exist_ok=True)
    detector = art_dir / "detector.py"
    detector.write_text(detector_body, encoding="utf-8")

    lock = root / ".atdd" / "substrate.lock.yaml"
    lock.write_text(
        "artifacts:\n"
        "  - id: atdd.workspace.python-pytest\n"
        "    version: 1.0.0\n"
        f"    installed_path: .atdd/workspaces/atdd.workspace.python-pytest/1.0.0\n"
        f"    digest: {_digest(detector_body)}\n"
        "    enabled: true\n",
        encoding="utf-8",
    )
    return detector


def test_e006_smoke_001_digest_mismatch_is_detected(run_enforce, tmp_path) -> None:
    proj = tmp_path / "tampered"
    detector = _vendored_substrate(proj, detector_body="def detect():\n    return []\n")
    # Tamper the vendored copy AFTER the lock recorded the original digest.
    detector.write_text("def detect():\n    return ['TAMPERED']\n", encoding="utf-8")

    proc = run_enforce(["--verify-substrate"], cwd=proj)
    combined = proc.stdout + proc.stderr

    # Load-bearing RED guard: the verb must be a real command.
    assert VERB_ABSENT not in combined, (
        "atdd enforce is not wired as a command — re-materialization guard absent"
    )
    # A vendored copy that no longer matches substrate.lock.yaml must fail the
    # digest guard (non-zero exit), proving the copies are guarded load-bearing code.
    assert proc.returncode != 0, (
        "a tampered vendored copy (digest mismatch vs substrate.lock.yaml) must "
        f"fail the re-materialization check; got exit {proc.returncode}:\n{combined}"
    )


def test_e006_smoke_001_intact_substrate_passes(run_enforce, tmp_path) -> None:
    proj = tmp_path / "intact"
    _vendored_substrate(proj, detector_body="def detect():\n    return []\n")

    proc = run_enforce(["--verify-substrate"], cwd=proj)
    combined = proc.stdout + proc.stderr

    assert VERB_ABSENT not in combined, "atdd enforce is not wired as a command"
    # Intact, digest-matched vendored trees pass the guard.
    assert proc.returncode == 0, (
        f"intact digest-matched substrate must pass; got exit {proc.returncode}:\n{combined}"
    )
