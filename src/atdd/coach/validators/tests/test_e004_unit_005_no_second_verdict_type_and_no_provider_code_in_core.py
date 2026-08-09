# URN: test:govern-registry:govern-registry:E004-UNIT-005-no-second-verdict-type-and-no-provider-code-in-core
# Acceptance: acc:govern-registry:E004-UNIT-005-no-second-verdict-type-and-no-provider-code-in-core
# WMBT: wmbt:govern-registry:E004
# Phase: GREEN
# Layer: unit
# Runtime: python
# Assertion: structural
# Purpose: GateVerdict is not imported, no second verdict enum is defined, and no provider or detector code is imported into core — asserted against a real import graph, not documented.
"""acc:govern-registry:E004-UNIT-005 — the structural commitments, executed.

Two promises this slice makes are the kind that hold perfectly in prose and rot
silently in code, so they are asserted rather than documented:

  * ``GateVerdict`` is not imported. Its four MEANINGS are reused, but the TYPE
    belongs to ``atdd.coach.gate``, and pulling a transition-gate type into the
    binding domain would make substrate/domain code import outward. This is
    precedent, not workaround — ``decision.py``'s own docstring records
    ``planner.interlocking.route_space`` reaching the same split independently
    and being "unimportable from here by the purity contract above, same shape".
  * No provider or detector code is imported into core. Core reads manifests,
    locks and RAW reports as DATA; provider execution stays subprocess-only.

The import graph is measured in a FRESH SUBPROCESS. Asserting against this
session's ``sys.modules`` would prove nothing: by the time these tests run, the
whole suite has imported half the toolkit, so any module would appear "already
imported" and the check would pass no matter what the module actually pulls in.
"""
from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest

import atdd
from atdd.coach.validators import _bound_realization as br
from atdd.coach.validators import test_rule_validator_binding as reverse

pytestmark = [pytest.mark.coach]

_MODULES = (
    "atdd.coach.validators._bound_realization",
    "atdd.coach.validators.test_rule_validator_binding",
)

#: The vendored substrate trees. Any module loaded from under these is provider
#: or detector code, and core importing one would breach the subprocess boundary.
_VENDORED_WORKSPACES = str(Path(".atdd") / "workspaces")
_VENDORED_EXTENSIONS = str(Path(".atdd") / "extensions")

_PROBE = """
import json, sys
for name in {modules!r}:
    __import__(name)
loaded = {{
    name: getattr(mod, "__file__", None)
    for name, mod in sys.modules.items()
    if getattr(mod, "__file__", None)
}}
print(json.dumps(loaded))
"""


def _imported_modules() -> dict:
    """Import the modules in a clean interpreter; return {name: file}."""
    repo_src = Path(atdd.__file__).resolve().parents[1]
    proc = subprocess.run(
        [sys.executable, "-c", _PROBE.format(modules=list(_MODULES))],
        capture_output=True,
        text=True,
        cwd=str(repo_src.parent),
        env={"PYTHONPATH": str(repo_src), "PATH": "/usr/bin:/bin", "HOME": str(Path.home())},
    )
    assert proc.returncode == 0, f"probe failed:\n{proc.stderr}"
    return json.loads(proc.stdout)


def _source_of(module) -> ast.Module:
    return ast.parse(Path(module.__file__).read_text(encoding="utf-8"))


def _imported_names(tree: ast.Module) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
            names.update(f"{node.module}.{a.name}" for a in node.names)
    return names


@pytest.mark.parametrize("module", (br, reverse), ids=lambda m: m.__name__)
def test_the_transition_gate_verdict_type_is_not_imported(module):
    """Meanings, not the type — asserted at the line that would import it."""
    imported = _imported_names(_source_of(module))
    offenders = sorted(n for n in imported if n.startswith("atdd.coach.gate"))
    assert offenders == [], (
        f"{module.__name__} imports {offenders} — the verdict MEANINGS are "
        f"reused here, but importing the transition-gate type would make "
        f"substrate/domain code import outward (#1772 Decisions 16-18)"
    )
    assert "GateVerdict" not in {n.rsplit(".", 1)[-1] for n in imported}


def test_no_gate_module_is_pulled_in_transitively():
    """Not imported directly, and not dragged in behind our back either."""
    loaded = _imported_modules()
    gate = sorted(n for n in loaded if n.startswith("atdd.coach.gate"))
    assert gate == [], (
        f"importing the proof modules transitively loads {gate}; the split is "
        f"only real if nothing on the path re-couples them"
    )


def test_no_provider_or_detector_code_is_imported_into_core():
    """Core reads the vendored substrate as data. It never imports it."""
    loaded = _imported_modules()
    vendored = sorted(
        f"{name} ({path})"
        for name, path in loaded.items()
        if _VENDORED_WORKSPACES in path or _VENDORED_EXTENSIONS in path
    )
    assert vendored == [], (
        f"provider/detector modules were imported into core: {vendored}. "
        f"Provider execution is subprocess-only; the proof resolver may read a "
        f"provider's manifest and locate its CLI, never import it."
    )


def test_the_proof_module_declares_its_public_surface():
    """A frozen interface a sibling issue builds against must state what it is."""
    assert hasattr(br, "__all__")
    for name in br.__all__:
        assert hasattr(br, name), f"__all__ names {name!r}, which does not exist"
    for promised in (
        "BoundRealizationProof",
        "BoundRealizationResolver",
        "OUTCOMES",
        "REFUSAL_BASES",
        "BASIS_OUTCOME",
    ):
        assert promised in br.__all__, f"{promised} is part of the frozen interface"
