"""DEPRECATED compatibility shim.

``PersonaShim`` moved to ``atdd.runtime.agent_control`` in Child 6
(docs/coach-decomposition.md §13.6; the runtime agent-control layer). This module
re-exports it so existing imports keep working through the deprecation soak.

Removal target: 3.87.0 (§11 compatibility deprecation cadence).
"""
from __future__ import annotations

import warnings

from atdd.runtime.agent_control._shim import PersonaShim, _UNSET  # noqa: F401

warnings.warn(
    "atdd.coach.shim.persona_shim is deprecated; import PersonaShim from "
    "atdd.runtime.agent_control (Child 6). Removal target: 3.87.0.",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = ["PersonaShim"]
