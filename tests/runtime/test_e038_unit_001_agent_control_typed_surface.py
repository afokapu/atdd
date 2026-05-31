# URN: test:govern-lifecycle:extract-runtime-agent-control-and-close-spawn-cluster:E038-UNIT-001-agent-control-typed-surface
# Acceptance: acc:govern-lifecycle:E038-UNIT-001-agent-control-typed-surface
# WMBT: wmbt:govern-lifecycle:E038
# Phase: RED
# Assertion: behavioral
# Layer: runtime
"""E038-UNIT-001 — typed surface of the extracted runtime agent-control layer.

docs/coach-decomposition.md §4.8 (AgentController + DispatchSpec), §4.9
(view-only Multiplexer Protocol), §3.3 (dependency rules). Child 6 ships
``atdd.runtime.agent_control`` and ``atdd.runtime.multiplexer``; this asserts
the public surface exists, the control-method ban holds, and neither runtime
layer imports a forbidden sibling/upper layer.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]

_SRC = Path(__file__).resolve().parents[2] / "src"


def test_agent_control_public_surface_importable():
    from atdd.runtime.agent_control import (  # noqa: F401
        AgentController,
        AgentEvent,
        AgentHandle,
        AgentSignal,
        DispatchSpec,
        ReadyResult,
    )

    # AgentController is a structural Protocol with the §4.8 method set.
    for method in ("spawn", "deliver_prompt", "wait_ready", "stream_events", "signal", "stop"):
        assert hasattr(AgentController, method), f"AgentController missing {method!r}"


def test_agent_signal_members():
    from atdd.runtime.agent_control import AgentSignal

    assert AgentSignal.INTERRUPT == "interrupt"
    assert AgentSignal.DONE_ACK == "done_ack"
    assert AgentSignal.PROMPT_ADDITIONAL == "prompt_additional"


def test_dispatchspec_is_frozen_with_spec_fields():
    import dataclasses

    from atdd.runtime.agent_control import DispatchSpec

    assert dataclasses.is_dataclass(DispatchSpec)
    field_names = {f.name for f in dataclasses.fields(DispatchSpec)}
    # §4.8 DispatchSpec field set.
    for required in (
        "agent_id",
        "persona",
        "worktree_path",
        "prompt_text",
        "correction_inbox",
        "output_log",
        "runtime_dir",
        "env_overrides",
        "transport",
        "permission_mode",
        "allowed_tools",
    ):
        assert required in field_names, f"DispatchSpec missing field {required!r}"

    spec = DispatchSpec(
        agent_id="coder-893-a",
        persona="coder",
        worktree_path=Path("/tmp/wt"),
        prompt_text="do the thing",
        correction_inbox=Path("/tmp/cli-return.jsonl"),
        output_log=Path("/tmp/output.log"),
        runtime_dir=Path("/tmp/rt"),
        env_overrides={"ATDD_AGENT_ID": "coder-893-a"},
        transport="cli-return",
        permission_mode="acceptEdits",
        allowed_tools=("Edit", "Bash"),
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        spec.agent_id = "mutated"  # type: ignore[misc]


def test_multiplexer_protocol_is_view_only():
    """§4.9: the view-only Multiplexer Protocol MUST NOT carry control methods."""
    from atdd.runtime.multiplexer import Multiplexer

    forbidden = {"paste_text", "send_key", "capture_pane_text"}
    methods = {name for name in dir(Multiplexer) if not name.startswith("_")}
    leaked = forbidden & methods
    assert not leaked, f"Multiplexer Protocol leaked control methods: {leaked}"
    # And it keeps its view-only surface.
    for view_method in ("attach_view", "list_surfaces", "close_surface", "list_workspaces"):
        assert hasattr(Multiplexer, view_method), f"Multiplexer missing {view_method!r}"


def _module_imports(py_file: Path) -> set[str]:
    tree = ast.parse(py_file.read_text())
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for n in node.names:
                imports.add(n.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return imports


@pytest.mark.parametrize(
    ("layer", "forbidden"),
    [
        (
            "atdd/runtime/agent_control",
            {"atdd.coach", "atdd.train", "atdd.integrations", "atdd.runtime.multiplexer"},
        ),
        (
            "atdd/runtime/multiplexer",
            {"atdd.coach", "atdd.train", "atdd.integrations", "atdd.runtime.agent_control"},
        ),
    ],
)
def test_runtime_layers_obey_import_discipline(layer: str, forbidden: set[str]):
    """§3.3 dependency rules — enforced directly on the new runtime layers."""
    layer_path = _SRC / layer
    py_files: list[Path]
    if layer_path.is_dir():
        py_files = [
            p for p in layer_path.rglob("*.py")
            if "/tests/" not in str(p) and not p.name.startswith("test_")
        ]
    else:
        py_files = [layer_path.with_suffix(".py")]

    assert py_files, f"layer {layer!r} produced no source files to scan"

    violations = []
    for py in py_files:
        if not py.exists():
            continue
        for imp in _module_imports(py):
            for fb in forbidden:
                if imp == fb or imp.startswith(fb + "."):
                    violations.append((py.name, imp, fb))
    assert not violations, "\n".join(
        f"{name} imports {imp!r} (forbidden: {fb})" for name, imp, fb in violations
    )
