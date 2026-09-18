# URN: test:coach:urn:contract_resolver_prefix_strip
"""ContractResolver strips the FAMILY PREFIX, not every occurrence of it (#2043).

``resolve`` used ``urn.replace("contract:", "")``, which removes the substring
wherever it recurs. For every identity in this repo that is harmless, because no
theme is named ``contract`` — which is exactly why the defect shipped and stayed
latent. Themes are consumer-overridable (``get_theme_map``,
``planner.artifact-naming.theme-taxonomy``), so a consumer repo may legitimately
name one ``contract``; its contracts then resolved to a truncated identity and
were reported as missing schemas that are sitting on disk at the right path.

Measured in ``docs/spikes/labs/2043-contract-id-spelling/`` (worlds 2 and 3).

The first test is the guard: it fails against ``str.replace`` and passes against
a leading-prefix strip. The second pins the behaviour the fix must not disturb.
"""
from __future__ import annotations

import json

from atdd.coach.utils.graph.resolver import ContractResolver


def _repo(tmp_path, identity: str, *segments: str):
    """A repo holding one contract schema whose ``$id`` is ``identity``."""
    d = tmp_path / "contracts"
    d.joinpath(*segments[:-1]).mkdir(parents=True, exist_ok=True)
    d.joinpath(*segments[:-1], f"{segments[-1]}.schema.json").write_text(
        json.dumps({
            "$schema": "http://json-schema.org/draft-07/schema#",
            "$id": identity,
            "title": "T",
            "version": "1.0.0",
            "type": "object",
        }),
        encoding="utf-8",
    )
    return tmp_path


def test_identity_whose_theme_is_named_contract_resolves(tmp_path):
    """The family prefix is stripped once, so a `contract`-themed identity survives.

    ``contract:contract:match:result`` is the URN of the bare identity
    ``contract:match:result``. Under ``str.replace`` the identity became
    ``match:result``, which names no file here, and the contract read as broken.
    """
    root = _repo(tmp_path, "contract:match:result", "contract", "match", "result")

    resolution = ContractResolver(root).resolve("contract:contract:match:result")

    assert resolution.error is None, resolution.error
    assert [p.name for p in resolution.resolved_paths] == ["result.schema.json"]
    assert resolution.is_deterministic


def test_ordinary_identity_still_resolves(tmp_path):
    """The common case — no recurrence of the prefix — is unchanged."""
    root = _repo(tmp_path, "commons:binding-lock", "commons", "binding-lock")

    resolution = ContractResolver(root).resolve("contract:commons:binding-lock")

    assert resolution.error is None, resolution.error
    assert [p.name for p in resolution.resolved_paths] == ["binding-lock.schema.json"]
