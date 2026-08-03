"""Immutable object identity — the ``wi_<ULID>`` uid (#1400 project-shared-state).

Identity is **always** the immutable uid, never the slug (spec §2.1, §10 rule 1).
The uid is minted once at create, is globally unique, is never reused, and is the
sole identity that names the projection file ``.atdd/state/projection/<uid>.yaml``.
Slug and title are mutable *display* metadata and must never drive identity or
file location — renaming one leaves the uid and the filename untouched (Y001).

The encoding is a ULID: a 48-bit millisecond timestamp followed by 80 bits of
randomness, rendered in Crockford Base32 (the ``I``/``L``/``O``/``U``-free
alphabet). That gives a 26-character body, matching the ``commons:projection-object``
contract's ``^wi_[0-9A-HJKMNP-TV-Z]{26}$`` pattern, and it sorts lexicographically
by mint time — useful for humans, never load-bearing for correctness.

The mint timestamp is *inside* the opaque uid, not a document field: a uid is not
a wall-clock leak (see :mod:`atdd.state.projection`'s determinism guard, C001).

Dependency discipline: stdlib only.
"""
from __future__ import annotations

import os
import re
import time
from typing import Optional

#: Crockford Base32 — 32 symbols, ``I``/``L``/``O``/``U`` excluded to survive
#: transcription. This is the ULID alphabet.
_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"

#: The uid namespace prefix for a work item.
UID_PREFIX = "wi_"

#: Bits/characters of each ULID half (48-bit time → 10 chars, 80-bit random → 16).
_TIME_CHARS = 10
_RANDOM_BYTES = 10
_RANDOM_CHARS = 16

#: The identity shape, byte-for-byte the ``commons:projection-object`` pattern.
UID_RE = re.compile(r"^wi_[0-9A-HJKMNP-TV-Z]{26}$")


class UidImmutableError(ValueError):
    """A write attempted to rewrite an already-minted uid (spec §7.1: immutable)."""


def _encode(value: int, length: int) -> str:
    """Render ``value`` as ``length`` Crockford Base32 characters, big-endian."""
    chars = [""] * length
    for i in range(length - 1, -1, -1):
        chars[i] = _CROCKFORD[value & 0x1F]
        value >>= 5
    return "".join(chars)


def mint_uid(
    *,
    timestamp_ms: Optional[int] = None,
    entropy: Optional[bytes] = None,
) -> str:
    """Mint a fresh, globally unique, never-reused work-item uid.

    ``timestamp_ms`` and ``entropy`` exist so a test can pin the value; production
    callers pass neither and get wall-clock milliseconds plus ``os.urandom``.
    Two mints inside the same millisecond still differ: the 80 random bits carry
    the uniqueness, the timestamp only carries the sort order.
    """
    ms = int(time.time() * 1000) if timestamp_ms is None else int(timestamp_ms)
    raw = os.urandom(_RANDOM_BYTES) if entropy is None else bytes(entropy)
    if len(raw) < _RANDOM_BYTES:
        raise ValueError(f"entropy must be >= {_RANDOM_BYTES} bytes, got {len(raw)}")
    body = _encode(ms, _TIME_CHARS) + _encode(
        int.from_bytes(raw[:_RANDOM_BYTES], "big"), _RANDOM_CHARS
    )
    return UID_PREFIX + body


def is_uid(value: object) -> bool:
    """True when ``value`` is a well-formed work-item uid."""
    return isinstance(value, str) and UID_RE.match(value) is not None


def assert_uid(value: object) -> str:
    """Return ``value`` if it is a well-formed uid; raise :class:`ValueError` otherwise."""
    if not is_uid(value):
        raise ValueError(f"not a work-item uid (expected {UID_RE.pattern}): {value!r}")
    return str(value)


def assert_uid_immutable(current: str, incoming: object) -> None:
    """Refuse a write that would rewrite ``current`` to a different uid.

    A no-op when ``incoming`` is ``None`` or already equals ``current`` — the
    guard exists to stop identity from moving, not to forbid restating it.
    """
    if incoming is None or incoming == current:
        return
    raise UidImmutableError(
        f"uid is immutable: refusing to rewrite {current!r} to {incoming!r}"
    )
