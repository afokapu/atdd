# URN: test:migrate-projection-authority:plan-migration-rollout:K001-SMOKE-001-collaborates-through-projection-only
# Acceptance: acc:migrate-projection-authority:K001-SMOKE-001-collaborates-through-projection-only
# WMBT: wmbt:migrate-projection-authority:K001
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: End-to-end — two real checkouts sharing a bare git remote, with GitHub unreachable (a `gh` shim that explodes) and .atdd/manifest.yaml absent, collaborate through the committed projection alone: A advances a work item and pushes, B pulls and reads that new phase, no GitHub call is ever attempted, and every core lifecycle command succeeds with no manifest present. Refs #1434.
"""SMOKE — two checkouts collaborate through the projection alone (K001-SMOKE-001).

wagon: migrate-projection-authority | feature: plan-migration-rollout | phase: SMOKE
WMBT: wmbt:migrate-projection-authority:K001

This is the wagon's thesis, executed. Everything else in M8 exists so that this can be true:

- two **real** checkouts, sharing a **bare** git remote that is not GitHub and knows nothing of it;
- a ``gh`` shim first on ``PATH`` that records any invocation and fails, so an attempted GitHub call
  is not merely unlikely — it is *detectable*, and it fails the test with the argv;
- **no** ``.atdd/manifest.yaml`` anywhere, so a surviving fallback reader cannot quietly rescue a
  read that should have come from the projection;
- **zero** providers registered.

Under those conditions, developer A advances a work item and pushes, and developer B — who has
never spoken to GitHub, and has no manifest — pulls and sees the new phase. The committed projection
is the only channel between them. If that works, the migration is real. Refs #1434 / #1400.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import yaml

_SRC = Path(__file__).resolve().parents[4]
_PROJECTION = Path(".atdd") / "state" / "projection"


def _arm_gh_trap(bin_dir: Path, witness: Path) -> None:
    bin_dir.mkdir(parents=True, exist_ok=True)
    shim = bin_dir / "gh"
    shim.write_text(
        "#!/bin/sh\n"
        f'echo "gh $*" >> "{witness}"\n'
        'echo "a lifecycle command called GitHub" >&2\n'
        "exit 97\n"
    )
    shim.chmod(0o755)


def _env(root: Path, bin_dir: Path) -> dict:
    return {
        "PYTHONPATH": str(_SRC),
        "PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}",
        "HOME": str(root),
        "CI": "true",
        "GH_TOKEN": "", "GITHUB_TOKEN": "",
    }


def _atdd(root: Path, bin_dir: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "atdd", "state", *args, "--root", str(root)],
        cwd=str(root), env=_env(root, bin_dir), capture_output=True, text=True, timeout=180,
    )


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    result = subprocess.run(["git", *args], cwd=str(root), capture_output=True, text=True,
                            timeout=60)
    assert result.returncode == 0, f"git {args}: {result.stderr}"
    return result


def _checkout(remote: Path, path: Path) -> Path:
    _git(path.parent, "clone", "--quiet", str(remote), str(path))
    _git(path, "config", "user.email", "dev@atdd.test")
    _git(path, "config", "user.name", "Dev")
    (path / ".atdd").mkdir(exist_ok=True)
    return path


def test_k001_smoke_001_collaborates_through_projection_only(tmp_path) -> None:
    """A advances and pushes; B pulls and sees it. No GitHub, no manifest, no provider."""
    bin_dir = tmp_path / "bin"
    witness = tmp_path / "gh-was-called.txt"
    _arm_gh_trap(bin_dir, witness)

    # A bare remote that is not GitHub and has never heard of it.
    remote = tmp_path / "remote.git"
    remote.mkdir()
    _git(remote, "init", "--bare", "--quiet", "--initial-branch", "main")

    # Seed it, so both checkouts share a main.
    seed = tmp_path / "seed"
    seed.mkdir()
    _git(seed, "init", "--quiet", "--initial-branch", "main")
    _git(seed, "config", "user.email", "dev@atdd.test")
    _git(seed, "config", "user.name", "Dev")
    (seed / ".atdd").mkdir()
    (seed / ".atdd" / "config.yaml").write_text("version: '1.0'\n", encoding="utf-8")
    # The developer's store is PRIVATE and gitignored — that is the scoped-truth rule (spec §1),
    # and it is why the committed projection has to exist at all. If the store travelled with the
    # branch, this whole wagon would be unnecessary.
    (seed / ".gitignore").write_text(
        ".atdd/state/state.sqlite*\n.atdd/version_cache.json\n", encoding="utf-8",
    )
    _git(seed, "add", "-A")
    _git(seed, "commit", "--quiet", "-m", "an atdd repo with no manifest")
    _git(seed, "remote", "add", "origin", str(remote))
    _git(seed, "push", "--quiet", "origin", "main")

    alice = _checkout(remote, tmp_path / "alice")
    bob = _checkout(remote, tmp_path / "bob")

    # No manifest anywhere. A surviving fallback reader cannot rescue anything here.
    for checkout in (alice, bob):
        assert not (checkout / ".atdd" / "manifest.yaml").exists()

    # Zero providers, in both checkouts.
    for checkout in (alice, bob):
        listed = _atdd(checkout, bin_dir, "providers")
        assert listed.returncode == 0, listed.stderr
        assert "no SyncProvider is registered" in listed.stdout

    # --- Alice creates a work item, projects it, and pushes -------------------------------
    assert _atdd(alice, bin_dir, "init").returncode == 0
    created = _atdd(alice, bin_dir, "object", "create", "--slug", "shared-widget",
                    "--owner", "alice")
    assert created.returncode == 0, created.stderr
    uid = created.stdout.strip()

    assert _atdd(alice, bin_dir, "project").returncode == 0
    _git(alice, "add", "-A")
    _git(alice, "commit", "--quiet", "-m", "create shared-widget")
    _git(alice, "push", "--quiet", "origin", "main")

    # --- Alice ADVANCES its phase and pushes again ---------------------------------------
    document = alice / _PROJECTION / f"{uid}.yaml"
    before = yaml.safe_load(document.read_text(encoding="utf-8"))
    assert before["phase"] == "INIT"

    advanced = _atdd(alice, bin_dir, "object", "transition", uid, "--phase", "PLANNED")
    if advanced.returncode != 0:
        # No transition verb in this surface — advance through the store the way the lifecycle
        # does, then re-project. The channel under test is the projection, not the verb.
        import sqlite3

        from atdd.state.manifest_import import WORK_ITEM_KIND
        from atdd.state.store import StateStore

        conn = sqlite3.connect(str(alice / ".atdd" / "state" / "state.sqlite"))
        conn.row_factory = sqlite3.Row
        try:
            store = StateStore(conn)
            obj = store.objects.get(uid)
            store.objects.upsert(uid, WORK_ITEM_KIND, state="PLANNED", data=dict(obj.data))
        finally:
            conn.close()

    assert _atdd(alice, bin_dir, "project").returncode == 0
    assert yaml.safe_load(document.read_text(encoding="utf-8"))["phase"] == "PLANNED"
    _git(alice, "add", "-A")
    _git(alice, "commit", "--quiet", "-m", "advance shared-widget to PLANNED")
    _git(alice, "push", "--quiet", "origin", "main")

    # --- Bob pulls, and reads Alice's new phase FROM THE COMMITTED PROJECTION -------------
    _git(bob, "pull", "--quiet", "origin", "main")

    bobs_copy = bob / _PROJECTION / f"{uid}.yaml"
    assert bobs_copy.is_file(), "B never received the work item"
    assert yaml.safe_load(bobs_copy.read_text(encoding="utf-8"))["phase"] == "PLANNED", (
        "B did not observe A's new phase from the committed projection alone"
    )

    # B can hydrate it into his own store and run every core lifecycle command — with no manifest,
    # no GitHub and no provider. This is the whole claim.
    for step in (("hydrate",), ("canonicality",), ("shadow",), ("digest",),
                 ("hot-path",), ("manifest-fallback",)):
        result = _atdd(bob, bin_dir, *step)
        assert result.returncode == 0, f"{step} failed for B: {result.stdout}{result.stderr}"

    # And the M8 cutover check passes, in B's checkout, over the projection A sent him.
    done = _atdd(bob, bin_dir, "cutover")
    assert done.returncode == 0, done.stdout + done.stderr
    assert "COMPLETE — all 3 exit criteria met" in done.stdout

    # Neither checkout ever attempted a GitHub call. Not once, across the whole exchange.
    assert not witness.exists(), f"a GitHub call was attempted: {witness.read_text()}"
