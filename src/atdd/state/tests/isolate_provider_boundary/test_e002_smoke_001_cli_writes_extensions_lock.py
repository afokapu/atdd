# URN: test:isolate-provider-boundary:lock-extension-digests:E002-SMOKE-001-cli-writes-extensions-lock
# Acceptance: acc:isolate-provider-boundary:E002-SMOKE-001-cli-writes-extensions-lock
# WMBT: wmbt:isolate-provider-boundary:E002
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: In a real checkout with the installed CLI and ZERO providers registered, `atdd state extensions-lock` writes a real .atdd/extensions.lock that validates against its authored schema, whose core block carries atdd_version and all three policy digests and whose providers block is present and empty — and `--verify` passes on it, then fails on a drifted extension. Refs #1400.
"""The lock is a real file the real CLI writes, in a real checkout (E002-SMOKE-001).

wagon: isolate-provider-boundary | feature: lock-extension-digests | phase: SMOKE
WMBT: wmbt:isolate-provider-boundary:E002

Zero providers, because that is the configuration core actually ships in and the one an operator
first meets: the lock has to be writable, valid, and *meaningful* before the first extension exists,
not after. A `providers: {}` block is the lock saying "this checkout has no extensions" — which a
reader must be able to tell apart from a lock that forgot to mention them.

Then the file is committed and `--verify` is run against a real extension that has drifted, because
a lock nobody checks is a lock that pins nothing. The verification is driven by the CLI and judged
by its exit code — the way CI would.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml

from ._live import (
    EXTENSION_SPEC,
    EXTENSION_SOURCE,
    atdd_state,
    gh_was_invoked,
    install_extension,
    repo_on_bare_remote,
)


@pytest.mark.smoke
def test_e002_smoke_001_cli_writes_extensions_lock(tmp_path) -> None:
    """The CLI writes a schema-valid lock with zero providers; --verify passes, then catches drift."""
    _remote, repo = repo_on_bare_remote(tmp_path)

    written = atdd_state(repo, "extensions-lock")

    assert written.returncode == 0, written.stdout + written.stderr
    lock_file = repo / ".atdd" / "extensions.lock"
    assert lock_file.is_file(), "the command must write a real file, not merely report one"

    document = yaml.safe_load(lock_file.read_text(encoding="utf-8"))
    contract = json.loads(
        (Path(__file__).resolve().parents[5] / "contracts" / "commons"
         / "provider-extensions-lock.schema.json").read_text(encoding="utf-8"))

    # It validates against its authored schema: every required key, no key the contract forbids.
    assert set(document) == set(contract["required"])
    assert document["schema_version"] == 1
    assert set(document["core"]) == set(contract["properties"]["core"]["required"])

    # The core block carries atdd_version and all three policy digests.
    assert document["core"]["atdd_version"]
    for key in ("projection_schema_digest", "lifecycle_policy_digest", "merge_policy_digest"):
        assert re.fullmatch(r"sha256:[0-9a-f]{64}", document["core"][key]), key

    # The providers block is PRESENT and EMPTY.
    assert "providers" in document
    assert document["providers"] == {}

    # --verify passes on what was just written.
    verified = atdd_state(repo, "extensions-lock", "--verify")
    assert verified.returncode == 0, verified.stdout + verified.stderr
    assert "verifies" in verified.stdout

    # Now a REAL extension is installed and pinned...
    extension = install_extension(tmp_path)
    relocked = atdd_state(repo, "extensions-lock", "--provider", EXTENSION_SPEC,
                          extension=extension)
    assert relocked.returncode == 0, relocked.stdout + relocked.stderr
    pinned = yaml.safe_load(lock_file.read_text(encoding="utf-8"))
    assert pinned["providers"]["demo"]["version"] == "2.1.0"
    assert pinned["providers"]["demo"]["digest"].startswith("sha256:")

    # ...and then it drifts: the same provider name, a different digest. The lock catches it, and
    # it catches it BEFORE the extension mirrors anything.
    drifted_source = EXTENSION_SOURCE.replace('DIGEST = "sha256:" + "ab" * 32',
                                              'DIGEST = "sha256:" + "cd" * 32')
    drifted = install_extension(tmp_path, drifted_source, name="drifted-ext")
    caught = atdd_state(repo, "extensions-lock", "--verify", "--provider", EXTENSION_SPEC,
                        extension=drifted)

    assert caught.returncode != 0, "a drifting extension must not verify"
    assert "EXTENSION DRIFT" in caught.stderr
    assert "demo" in caught.stderr

    assert gh_was_invoked(repo) == []
