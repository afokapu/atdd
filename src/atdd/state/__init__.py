"""ATDD State Store — local SQLite-backed operational data (umbrella #1168).

This package is the foundational substrate for ATDD's *operational truth*: the
durable, queryable local state (work items, phase/status, worktree bindings,
external references, sync inbox/outbox, runtime checkpoints) that today is
scattered across ``.atdd/manifest.yaml``, GitHub labels/Projects, and runtime
files. It is independent of the Hub (#1096), which will consume it as a domain.

Phase 1 (#1177/#1179) shipped the **layout substrate**: the Control Root
resolver and the ``atdd state doctor`` / ``atdd state layout --check`` commands.
Phase 2 (#1181) adds the **SQLite schema + migration runner** and
``atdd state init``. Typed storage APIs, manifest import, and provider sync land
in later phases (#1168 Phases 3-6).

Source-of-truth boundary (#1168):

- **git-tracked protocol files** (plan/, conventions, validators, schemas) are
  protocol truth;
- the **State Store** (``<control-root>/.atdd/state/state.sqlite``) is local
  operational truth;
- **external providers** (GitHub, cmux, …) are external side-effect truth,
  recorded through external references / sync records.

Dependency discipline: this package imports only stdlib (``pathlib``, ``os``,
``logging``, ``sqlite3``). It MUST NOT import ``atdd.coach.*``, ``atdd.train.*``,
or ``atdd.integrations.*`` — callers translate their context into the primitive
arguments these APIs accept.
"""
from __future__ import annotations

from atdd.state.db import (
    apply_migrations,
    connect,
    current_version,
    init_state_store,
)
from atdd.state.migrations import CORE_MIGRATIONS, Migration, latest_version
from atdd.state.paths import (
    AmbiguousControlRootError,
    ControlRootNotFoundError,
    ControlRootResolution,
    LayoutMode,
    check_layout,
    is_control_root,
    is_scratch_atdd,
    resolve_control_root,
)

__all__ = [
    "AmbiguousControlRootError",
    "CORE_MIGRATIONS",
    "ControlRootNotFoundError",
    "ControlRootResolution",
    "LayoutMode",
    "Migration",
    "apply_migrations",
    "connect",
    "current_version",
    "init_state_store",
    "latest_version",
    "check_layout",
    "is_control_root",
    "is_scratch_atdd",
    "resolve_control_root",
]
