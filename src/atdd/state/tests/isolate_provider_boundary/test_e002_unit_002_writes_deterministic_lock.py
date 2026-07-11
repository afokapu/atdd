# URN: test:isolate-provider-boundary:lock-extension-digests:E002-UNIT-002-writes-deterministic-lock
# Acceptance: acc:isolate-provider-boundary:E002-UNIT-002-writes-deterministic-lock
# WMBT: wmbt:isolate-provider-boundary:E002
# Phase: GREEN
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: The writer emits schema_version 1, core.atdd_version and all three policy digests, and name-sorted provider entries each carrying a version and a sha256 digest — byte-identical across two runs over the same logical inputs, carrying no secret material, and conforming to the authored commons:provider-extensions-lock contract. Refs #1400.
"""The lock is deterministic, contract-shaped, and says nothing it should not (E002-UNIT-002).

wagon: isolate-provider-boundary | feature: lock-extension-digests | phase: GREEN
WMBT: wmbt:isolate-provider-boundary:E002

``zeta`` is registered before ``alpha`` again, so a writer that emitted providers in registration
order would produce different bytes here than one that sorted them — and a lock whose bytes depend
on the order two extensions were installed in is a lock that conflicts on every merge for no
reason, which is a lock people delete.

The digests are checked for what they *are*, not merely that they exist: each one is recomputed
from the policy it claims to pin, so a writer that shipped a constant, or hashed the wrong table,
fails here rather than in six months when an extension drifts and nothing notices.

The contract is the authored ``commons:provider-extensions-lock``, read off disk. The lock this
code writes and the lock the contract describes are checked against each other rather than assumed
to agree.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

from atdd.state import extensions_lock, provider_seam
from atdd.state.secrets import scan

from ._seam import StubProvider, factory


def _contract() -> dict:
    repo = Path(__file__).resolve().parents[5]
    return json.loads(
        (repo / "contracts" / "commons" / "provider-extensions-lock.schema.json")
        .read_text(encoding="utf-8")
    )


def test_e002_unit_002_writes_deterministic_lock(tmp_path) -> None:
    """Two runs, byte-identical output; providers name-sorted; every core digest present and right."""
    zeta = StubProvider(name="zeta", version="0.9.0", body="zeta-v1")
    alpha = StubProvider(name="alpha", version="3.2.1", body="alpha-v1")
    provider_seam.register_provider("zeta", factory(zeta))
    provider_seam.register_provider("alpha", factory(alpha))
    providers = provider_seam.discover_providers()

    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()

    path_one = extensions_lock.write_lock(first, providers)
    path_two = extensions_lock.write_lock(second, providers)

    # Byte-identical across runs. Not "equal when parsed" — the same bytes, which is what a
    # committed, diffed, merged file has to be.
    assert path_one.read_bytes() == path_two.read_bytes()

    document = yaml.safe_load(path_one.read_text(encoding="utf-8"))

    assert document["schema_version"] == 1
    assert document["core"]["atdd_version"] == extensions_lock.core_version()

    # The three core digests are each the digest OF THE POLICY THEY NAME — recomputed here, not
    # trusted. A writer that emitted a constant would pass an existence check and fail this one.
    assert document["core"]["projection_schema_digest"] == extensions_lock.projection_schema_digest()
    assert document["core"]["lifecycle_policy_digest"] == extensions_lock.lifecycle_policy_digest()
    assert document["core"]["merge_policy_digest"] == extensions_lock.merge_policy_digest(first)
    for key in extensions_lock.CORE_DIGESTS:
        assert re.fullmatch(r"sha256:[0-9a-f]{64}", document["core"][key]), key

    # Provider entries are NAME-SORTED, though zeta was registered first.
    assert list(document["providers"]) == ["alpha", "zeta"]
    assert document["providers"]["alpha"] == {"version": "3.2.1", "digest": alpha.digest().digest}
    assert document["providers"]["zeta"] == {"version": "0.9.0", "digest": zeta.digest().digest}

    # And it verifies against the providers it pins.
    report = extensions_lock.verify(document, providers, root=first)
    assert report.ok, report.render()


def test_e002_unit_002_the_lock_conforms_to_its_authored_contract(tmp_path) -> None:
    """The lock core writes and the contract core authored describe the same document."""
    provider_seam.register_provider("demo", factory(StubProvider(name="demo")))
    path = extensions_lock.write_lock(tmp_path, provider_seam.discover_providers())
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    contract = _contract()

    assert set(document) == set(contract["required"]) == {"schema_version", "core", "providers"}
    assert set(document["core"]) == set(contract["properties"]["core"]["properties"])
    assert set(document["core"]) >= set(contract["properties"]["core"]["required"])

    digest_pattern = contract["properties"]["core"]["properties"]["projection_schema_digest"]["pattern"]
    for key in extensions_lock.CORE_DIGESTS:
        assert re.match(digest_pattern, document["core"][key])

    entry_schema = contract["properties"]["providers"]["additionalProperties"]
    for name, entry in document["providers"].items():
        assert set(entry) == set(entry_schema["properties"]) == {"version", "digest"}
        assert re.match(entry_schema["properties"]["digest"]["pattern"], entry["digest"]), name


def test_e002_unit_002_the_lock_carries_no_secret_material(tmp_path) -> None:
    """A lock is committed. Anything a provider put in it is in the history forever (I8, §10 rule 6)."""
    provider_seam.register_provider("demo", factory(StubProvider(name="demo")))
    path = extensions_lock.write_lock(tmp_path, provider_seam.discover_providers())
    text = path.read_text(encoding="utf-8")

    report = scan(trailers={"lock": text}, documents={})

    assert report.ok, report.render()
    # A digest is the one admissible form of "something derived from a secret": it commits to a
    # value without carrying it.
    assert "sha256:" in text


def test_e002_unit_002_with_zero_providers_the_block_is_present_and_empty(tmp_path) -> None:
    """"No extensions" is a fact the lock STATES; it must not look like a forgotten block."""
    path = extensions_lock.write_lock(tmp_path)
    document = yaml.safe_load(path.read_text(encoding="utf-8"))

    assert document["providers"] == {}
    assert "providers" in document
    assert extensions_lock.verify(document, {}, root=tmp_path).ok
