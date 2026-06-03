"""WorkerRegistry adapter backed by a static surface->worker map.

MVP source is ``.atdd/decision/registry.yaml`` (a flat surface->worker table).
A later follow-up (out of scope for #955) derives this from live
``.atdd/runtime`` state.
"""
from __future__ import annotations

from typing import Dict, Mapping, Optional

from atdd.mediate_worker_decisions.sense_decision.src.domain.decision_request import (
    WorkerRef,
)


class RegistryWorkerLookup:
    def __init__(self, workers: Mapping[str, Mapping[str, str]]) -> None:
        # workers: {surface_id: {run_id?, agent_handle_ref?}}
        self._by_surface: Dict[str, Mapping[str, str]] = dict(workers)

    def resolve(self, surface_id: str) -> Optional[WorkerRef]:
        entry = self._by_surface.get(surface_id)
        if entry is None:
            return None
        return WorkerRef(
            surface_id=surface_id,
            run_id=entry.get("run_id"),
            agent_handle_ref=entry.get("agent_handle_ref"),
        )

    @classmethod
    def from_config(cls, config: Mapping[str, object]) -> "RegistryWorkerLookup":
        """Build from a parsed ``.atdd/decision/registry.yaml`` mapping.

        Shape: ``workers: {<name>: {surface_id, run_id?, agent_handle_ref?}}``.
        """
        workers_cfg = config.get("workers", {}) if isinstance(config, dict) else {}
        by_surface: Dict[str, Mapping[str, str]] = {}
        if isinstance(workers_cfg, dict):
            for entry in workers_cfg.values():
                if isinstance(entry, dict) and entry.get("surface_id"):
                    by_surface[str(entry["surface_id"])] = {
                        k: str(v)
                        for k, v in entry.items()
                        if k in ("run_id", "agent_handle_ref")
                    }
        return cls(by_surface)
