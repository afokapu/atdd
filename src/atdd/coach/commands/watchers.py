"""Coach v9 J5 watchers — public re-export module.

The three watcher implementations live in dedicated submodules so each
matches one ``produce`` entry on the ``drive-state-machine`` wagon
(``runtime-event-watcher``, ``git-event-watcher``, ``liveness-checker``).
The shared queue lives next to them in ``event_queue``.

Re-exporting here keeps ``from atdd.coach.commands.watchers import …``
stable for downstream consumers (#L1 observer, #J6 resume runner) while
the implementation is split.
"""
from __future__ import annotations

from atdd.coach.commands.event_queue import (
    CoachEventQueue,
    NATURAL_KEY,
    REPLAY_BEHAVIOR,
    natural_key,
)
from atdd.coach.commands.git_watcher import GitWatcher, parse_commit_trailers
from atdd.coach.commands.liveness_checker import LivenessChecker
from atdd.coach.commands.runtime_watcher import RuntimeWatcher

__all__ = [
    "CoachEventQueue",
    "GitWatcher",
    "LivenessChecker",
    "NATURAL_KEY",
    "REPLAY_BEHAVIOR",
    "RuntimeWatcher",
    "natural_key",
    "parse_commit_trailers",
]
