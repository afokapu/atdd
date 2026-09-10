"""Shared harness for E072: a real git repo, the shipped registry hook blocks, and
a stubbed ``atdd`` whose drift/heal behaviour the test controls.

The hook blocks are extracted from the shipped templates rather than copied into
the test, so a test can never pass against a hook body that is no longer shipped.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[6]
HOOKS_DIR = REPO_ROOT / "src" / "atdd" / "coach" / "templates" / "hooks"

MIRRORS = ("plan/_wagons.yaml", "plan/_trains.yaml", "contracts/_artifacts.yaml")

_STUB = """#!/usr/bin/env bash
# Stub of the atdd CLI, controlled by marker files in the repo root.
if [ "$1" = "registry" ] && [ "$2" = "update" ]; then
  case "$3" in
    --check) if [ -f .drift ]; then echo "drift: plan/_wagons.yaml"; exit 1; fi; exit 0 ;;
    --yes)   if [ -f .healfails ]; then echo "resync failed"; exit 1; fi
             rm -f .drift; echo "total: 12" > plan/_wagons.yaml; echo "resynced"; exit 0 ;;
  esac
fi
exit 0
"""


def extract_block(hook_name: str, heading: str) -> str:
    """Return the shipped hook's block starting at ``heading``, up to its closing fi."""
    text = (HOOKS_DIR / hook_name).read_text(encoding="utf-8")
    if heading not in text:
        raise AssertionError(
            f"{hook_name} no longer contains a block headed {heading!r}.\n"
            "If it was deliberately removed, the acceptance that requires it must "
            "change too — a hook that does not carry this block cannot satisfy E072."
        )
    start = text.index(heading)
    end = text.index("\nfi\n", text.index("\nif ", start)) + len("\nfi\n")
    return text[start:end]


def make_repo(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    """A real git repo with mirrors committed, plus an env whose PATH holds the stub."""
    repo = tmp_path / "repo"
    (repo / "plan").mkdir(parents=True)
    (repo / "contracts").mkdir(parents=True)
    (repo / "plan" / "_wagons.yaml").write_text("total: 11\n", encoding="utf-8")
    (repo / "plan" / "_trains.yaml").write_text("trains: []\n", encoding="utf-8")
    (repo / "contracts" / "_artifacts.yaml").write_text("artifacts: []\n", encoding="utf-8")
    (repo / "source.yaml").write_text("v1\n", encoding="utf-8")

    bindir = tmp_path / "bin"
    bindir.mkdir()
    stub = bindir / "atdd"
    stub.write_text(_STUB, encoding="utf-8")
    stub.chmod(0o755)

    for args in (["init", "-q", "-b", "main"], ["add", "-A"]):
        subprocess.run(["git", "-C", str(repo), *args], check=True)
    for k, v in (("user.email", "e072@lab"), ("user.name", "e072")):
        subprocess.run(["git", "-C", str(repo), "config", k, v], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "base"], check=True)

    import os
    env = {**os.environ, "PATH": f"{bindir}:{os.environ['PATH']}", "CI": ""}
    env.pop("GIT_DIR", None)
    return repo, env


def run_block(block: str, repo: Path, env: dict[str, str]):
    return subprocess.run(
        ["bash", "-c", block], cwd=str(repo), env=env,
        capture_output=True, text=True,
    )
