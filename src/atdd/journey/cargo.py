"""Cargo: the sole inter-wagon channel for the journey engine (#1042 / #1034).

An in-memory, accumulating envelope of contract-validated artifacts keyed by
``artifact_urn``. The runner threads it through the sequence; wagons communicate
ONLY through it (never via cross-wagon imports). The step-scoped declared-IO
guard (a wagon may read only its step's ``consumes`` and write only its
``primary``/``aux``) is layered on by #1044; this core provides the accumulating
channel + the access primitives. Stdlib-only (boundaries §3.3).
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, Optional


class CargoKeyError(KeyError):
    """Raised when an artifact is requested that is not present in cargo."""


class Cargo:
    def __init__(self, initial: Optional[Dict[str, Any]] = None) -> None:
        self._artifacts: Dict[str, Any] = dict(initial or {})

    def add_artifact(self, urn: str, data: Any) -> None:
        """Merge a produced artifact into cargo (accumulating; last write wins)."""
        self._artifacts[urn] = data

    def get_artifact(self, urn: str) -> Any:
        if urn not in self._artifacts:
            raise CargoKeyError(urn)
        return self._artifacts[urn]

    def has_artifact(self, urn: str) -> bool:
        return urn in self._artifacts

    def merge(self, produced: Dict[str, Any]) -> None:
        for urn, data in produced.items():
            self.add_artifact(urn, data)

    def urns(self) -> Iterable[str]:
        return tuple(self._artifacts.keys())

    def as_dict(self) -> Dict[str, Any]:
        """A shallow copy of the current artifact map (the wagon ``inputs``)."""
        return dict(self._artifacts)
