"""Hermetic fakes for enforce-surface-conformance tests (issue #865).

No real multiplexer: the layout port + scope probe + logger are recorded so tests
assert that a REAL layout primitive was invoked (not a print) and that
never-collapse holds. The RecordingBackend drives the flat-wagon shim end-to-end.
"""
from __future__ import annotations

from typing import Any

# Backend method names that count as a real layout MUTATION (not a read, not a
# rename, not a print). The print-theater guard asserts at least one fires.
LAYOUT_METHODS: frozenset[str] = frozenset(
    {
        "create_right_pane",
        "place_surface_right",
        "new_right_pane",
        "new_surface_in_pane",
        "move_surface",
        "new_surface",
        "new_pane",
        "split_pane",
    }
)


class RecordingLayoutPort:
    """Records MultiplexerLayoutPort calls; returns stable refs."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple, dict]] = []

    def create_right_pane(self, from_pane: str, *, workspace_id: str) -> str:
        self.calls.append(("create_right_pane", (from_pane,), {"workspace_id": workspace_id}))
        return f"pane:right:{workspace_id}"

    def place_surface_right(self, surface_ref: str, *, workspace_id: str, pane_ref: str) -> None:
        self.calls.append(
            ("place_surface_right", (surface_ref,), {"workspace_id": workspace_id, "pane_ref": pane_ref})
        )

    @property
    def layout_invocations(self) -> int:
        return len(self.calls)


class FakeScopeProbe:
    """Returns the configured worker identities per workspace."""

    def __init__(self, identities_by_workspace: dict[str, list[str]]) -> None:
        self._by_ws = identities_by_workspace
        self.queried: list[str] = []

    def list_identities(self, workspace_id: str) -> list[str]:
        self.queried.append(workspace_id)
        return list(self._by_ws.get(workspace_id, []))


class FakeLogger:
    def __init__(self) -> None:
        self.emits: list[tuple[str, str]] = []

    def emit(self, message: str, *, rule_id: str) -> None:
        self.emits.append((message, rule_id))


class RecordingBackend:
    """Generic multiplexer-backend double: records every method call by name.

    ``rename`` is concrete (the flat shim calls it). Any other attribute resolves
    to a recorder that captures the call and returns a stable ref string, so the
    GREEN shim's layout primitives are observable here.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple, dict]] = []

    def rename(self, ref: str, name: str) -> None:
        self.calls.append(("rename", (ref, name), {}))

    def call_names(self) -> list[str]:
        return [c[0] for c in self.calls]

    def layout_calls(self) -> list[str]:
        return [n for n in self.call_names() if n in LAYOUT_METHODS]

    def __getattr__(self, item: str) -> Any:
        # Only invoked for attributes not set on the instance/class.
        def _recorder(*args: Any, **kwargs: Any) -> str:
            self.calls.append((item, args, kwargs))
            return f"{item}:ref"

        return _recorder
