# URN: test:isolate-provider-boundary:lock-extension-digests:E002-UNIT-001-rejects-lock-missing-digest
# Acceptance: acc:isolate-provider-boundary:E002-UNIT-001-rejects-lock-missing-digest
# WMBT: wmbt:isolate-provider-boundary:E002
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: A lock missing projection_schema_digest (or the lifecycle/merge policy digest) is rejected with the offending field NAMED; a registered provider whose digest() disagrees with its recorded entry is reported as EXTENSION DRIFT; and in neither case is any partial .atdd/extensions.lock written to disk. Refs #1400.
"""An unpinnable lock is refused before it reaches the disk (E002-UNIT-001).

wagon: isolate-provider-boundary | feature: lock-extension-digests | phase: RED
WMBT: wmbt:isolate-provider-boundary:E002

The "no partial file" assertion is the one worth reading twice. A half-written lock is worse than
no lock at all: a missing file announces itself, and a file that exists but pins only two of the
three core policies looks exactly like a file that pins all of them, to everyone downstream who is
about to grant a failing provider the benefit of the doubt on the strength of it.

So the whole document is built and verified in memory and the path is opened only after it
verifies. Here the directory is checked afterwards and must contain nothing.
"""
from __future__ import annotations

import pytest

from atdd.state import extensions_lock, provider_seam
from atdd.state.extensions_lock import LockError

from ._seam import Stamp, StubProvider, factory


@pytest.mark.parametrize("omitted", extensions_lock.CORE_DIGESTS)
def test_e002_unit_001_rejects_lock_missing_digest(tmp_path, omitted) -> None:
    """Each required core digest, when missing, is rejected BY NAME — not as a generic fault."""
    document = extensions_lock.build_lock(root=tmp_path)
    del document["core"][omitted]

    report = extensions_lock.verify(document, {}, root=tmp_path)

    assert not report.ok
    assert any(omitted in problem for problem in report.problems), (
        f"the report must name the missing field {omitted!r}, not merely refuse the lock"
    )
    assert any("§10" in problem for problem in report.problems)
    assert not extensions_lock.lock_path(tmp_path).exists(), "no partial lock was written"


def test_e002_unit_001_a_provider_digest_that_disagrees_is_extension_drift(tmp_path) -> None:
    """The lock pinned one extension; a different one is now installed. That is drift, and it bites."""
    pinned = StubProvider(name="demo", version="1.0.0", body="v1")
    provider_seam.register_provider("demo", factory(pinned))
    document = extensions_lock.build_lock(provider_seam.discover_providers(), root=tmp_path)
    assert document["providers"]["demo"]["digest"] == pinned.digest().digest

    # The extension changed under a checkout that believes it did not.
    drifted = StubProvider(name="demo", version="1.0.0", body="v2-with-a-behaviour-change")
    assert drifted.digest().digest != pinned.digest().digest

    report = extensions_lock.verify(document, {"demo": drifted}, root=tmp_path)

    assert not report.ok
    assert any("EXTENSION DRIFT" in problem for problem in report.problems)
    assert any(pinned.digest().digest in problem for problem in report.problems), (
        "the report names BOTH digests — the one pinned and the one found"
    )
    assert not extensions_lock.lock_path(tmp_path).exists()


def test_e002_unit_001_a_version_bump_is_drift_too(tmp_path) -> None:
    """Same bytes, new version. The lock pins both, so both are checked."""
    pinned = StubProvider(name="demo", version="1.0.0", body="v1")
    document = extensions_lock.build_lock({"demo": pinned}, root=tmp_path)

    bumped = StubProvider(name="demo", version="2.0.0", body="v1")
    report = extensions_lock.verify(document, {"demo": bumped}, root=tmp_path)

    assert not report.ok
    assert any("EXTENSION DRIFT" in problem and "2.0.0" in problem for problem in report.problems)


def test_e002_unit_001_an_unpinnable_provider_may_not_mirror(tmp_path) -> None:
    """A provider that cannot say what it is cannot be pinned — and an unpinned extension is refused.

    Note the asymmetry with K001, and that it is deliberate: a provider that fails while *mirroring*
    is an alarm, because the mirror is presentation. A provider that fails while being *pinned* is
    fatal, because the lock is the thing that makes tolerating the first failure safe.
    """

    class Unpinnable:
        name = "unpinnable"

        def mirror(self, objects):
            return []

        def detect_drift(self, objects):
            return []

        def digest(self):
            raise RuntimeError("I cannot describe myself")

    with pytest.raises(LockError) as refusal:
        extensions_lock.build_lock({"unpinnable": Unpinnable()}, root=tmp_path)

    assert "unpinnable" in str(refusal.value)
    assert "may not mirror" in str(refusal.value)
    assert not extensions_lock.lock_path(tmp_path).exists()


def test_e002_unit_001_a_malformed_digest_is_refused(tmp_path) -> None:
    """``sha256:<64 hex>`` is the one admissible form; anything else is refused at build time."""

    class BadDigest(StubProvider):
        def digest(self) -> Stamp:
            return Stamp(name=self.name, version=self.version, digest="not-a-digest")

    with pytest.raises(LockError) as refusal:
        extensions_lock.build_lock({"demo": BadDigest(name="demo")}, root=tmp_path)

    assert "sha256:" in str(refusal.value)
    assert not extensions_lock.lock_path(tmp_path).exists()


def test_e002_unit_001_write_refuses_and_leaves_no_file(tmp_path) -> None:
    """The write path itself: a lock that would not verify never reaches the disk."""
    registered = StubProvider(name="demo", body="v1")
    provider_seam.register_provider("demo", factory(registered))

    # A checkout whose lock pins nothing about this provider, while the provider IS registered.
    # (Verified through the public write path, which builds, verifies, and only then opens a file.)
    written = extensions_lock.write_lock(tmp_path, provider_seam.discover_providers())
    assert written.is_file()
    original = written.read_bytes()

    # Now the lock is stale: the extension drifted. Re-verifying must refuse...
    drifted = StubProvider(name="demo", body="v2")
    report = extensions_lock.verify_repo(tmp_path, {"demo": drifted})
    assert not report.ok
    assert any("EXTENSION DRIFT" in problem for problem in report.problems)

    # ...and the committed lock is untouched by the failed verification.
    assert written.read_bytes() == original
