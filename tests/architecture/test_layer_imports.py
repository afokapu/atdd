# URN: test:govern-lifecycle:add-lifecycle-parity-and-import-discipline-tests:import-discipline
# Source of truth: docs/coach-decomposition.md §3.3, §10.2, Appendix A
"""Import-discipline test (required-CI from #889 onward, §10.2 / §20.3).

Enforces the §3.3 ``FORBIDDEN_BY_LAYER`` dependency table by static AST analysis:
each decomposition layer under ``src/atdd`` is scanned for imports it MUST NOT
make. Layers that have not been extracted yet (their directory does not exist)
contribute zero files and therefore pass trivially — the gate tightens
automatically as Children 4–10 land each layer.

This is the Appendix A test with one deliberate, spec-aligned guard:

* ``test_coach_core_has_no_io_at_import_time`` is kept verbatim — coach.core
  ships in Child 1, so it runs (and passes) from this PR onward.

``test_multiplexer_protocol_has_no_control_methods`` was retired by #1480 along
with ``atdd.runtime.multiplexer`` itself: with the Protocol pruned from core
there is no surface left to assert a control-method ban against.
"""
import ast
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src"

FORBIDDEN_BY_LAYER = {
    "atdd.coach.core": {
        "subprocess", "os.system", "requests", "urllib.request", "urllib3",
        "git", "gh", "cmux", "threading", "multiprocessing", "asyncio",
        "atdd.runtime", "atdd.integrations", "atdd.train", "atdd.observer",
    },
    "atdd.train": {
        "atdd.cli", "atdd.observer",
    },
    "atdd.runtime.worktree": {
        "atdd.coach", "atdd.train", "atdd.integrations",
    },
    # #1480 pruned atdd.runtime.agent_control and atdd.runtime.multiplexer from
    # core (worker management is not lifecycle governance), so their layer
    # entries — and the sibling-import ban between them — are retired with them.
    "atdd.integrations.github": {
        "atdd.coach", "atdd.train", "atdd.runtime",
    },
    # ATDD State Store (#1168): the foundational-layer import discipline previously
    # asserted here ("atdd.state" must not import coach/train/integrations/runtime/
    # observer) migrated to the node-bound validator
    # `coder.state-store.core-imports-no-providers`
    # (src/atdd/coder/validators/test_state_store_invariants.py), so the rule is
    # surfaced in `atdd validate` rather than living only as a structural gate (#1220).
}


def _module_imports(py_file: Path) -> set[str]:
    tree = ast.parse(py_file.read_text())
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for n in node.names:
                imports.add(n.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.add(node.module)
    return imports


def _layer_files(layer: str) -> list[Path]:
    layer_dir = SRC / layer.replace(".", "/")
    if not layer_dir.is_dir():
        return []
    return [p for p in layer_dir.rglob("*.py")
            if "/tests/" not in str(p) and not p.name.startswith("test_")]


@pytest.mark.parametrize("layer", sorted(FORBIDDEN_BY_LAYER.keys()))
def test_layer_has_no_forbidden_imports(layer: str):
    forbidden = FORBIDDEN_BY_LAYER[layer]
    violations = []
    for py in _layer_files(layer):
        for imp in _module_imports(py):
            for fb in forbidden:
                if imp == fb or imp.startswith(fb + "."):
                    violations.append((py, imp, fb))
    assert not violations, "\n".join(
        f"{p.relative_to(REPO_ROOT)} imports {imp!r} (forbidden: {fb})"
        for p, imp, fb in violations
    )


def test_coach_core_has_no_io_at_import_time():
    """Sanity: importing coach.core fresh must not pull subprocess into sys.modules.

    The check runs in a fresh interpreter (Child 1's acceptance command). Doing
    it in-process is meaningless: pytest and the atdd plugin import subprocess
    before this test ever runs, so a same-process ``sys.modules`` check can never
    be clean. A child process is the only faithful way to assert the import-time
    purity of ``atdd.coach.core``.
    """
    probe = (
        f"import sys; sys.path.insert(0, {str(SRC)!r}); "
        "import atdd.coach.core; "
        "sys.exit(1 if 'subprocess' in sys.modules else 0)"
    )
    # -I isolates the interpreter (ignores env vars + user site); inserting SRC
    # first guarantees we import the source coach.core, not an installed build.
    result = subprocess.run(
        [sys.executable, "-I", "-c", probe],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        "atdd.coach.core leaked subprocess (or failed to import) in a fresh interpreter:\n"
        f"stdout={result.stdout!r}\nstderr={result.stderr!r}"
    )
