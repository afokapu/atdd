# URN: component:govern-lifecycle:enforcement-substrate:rule_validator_resolver:backend:domain
# Runtime: python
# Purpose: AST-resolve a rule's `validator: <module>::<func>` reference to a callable + AST node.

"""Reverse-coherence resolver (issue #399 Phase 3).

A rule declares its enforcer with a single string of the form
``<module_basename>::<function_name>``. This module turns that string into:

    1. The validator file path (``atdd.<archetype>.validators.<module>.py``).
    2. The ``ast.FunctionDef`` node for ``<function_name>`` inside that file.
    3. The set of literal ``bind_rule("<id>")`` arguments seen inside the
       function body.

We AST-parse the validator file as TEXT — we do NOT import it. A single
broken validator must not break the entire reverse-coherence pass. The
resolver therefore degrades to a structured failure record rather than
raising at module-load time.

The dotted-import path is INFERRED from the rule's archetype:

    archetype="coder"  →  src/atdd/coder/validators/<module>.py
    archetype="coach"  →  src/atdd/coach/validators/<module>.py
    archetype="tester" →  src/atdd/tester/validators/<module>.py
    archetype="planner"→  src/atdd/planner/validators/<module>.py
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Set

import atdd


_ATDD_PKG_DIR = Path(atdd.__file__).resolve().parent

_VALID_ARCHETYPES = {"coder", "coach", "tester", "planner"}


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------
class ValidatorResolutionError(LookupError):
    """Raised when ``<module>::<function>`` cannot be resolved to an AST node."""


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ResolvedValidator:
    """Outcome of resolving a single ``module::function`` reference.

    Attributes:
        module_basename: The module filename (without ``.py``).
        function_name: The function name inside the module.
        archetype: One of ``coder``/``coach``/``tester``/``planner``.
        module_path: Absolute path to the validator file.
        function_node: The :class:`ast.FunctionDef` for the named function.
        bound_rule_ids: Literal string arguments passed to ``bind_rule(...)``
            inside the function body. May contain multiple ids if the
            validator binds more than one rule.
    """

    module_basename: str
    function_name: str
    archetype: str
    module_path: Path
    function_node: ast.FunctionDef
    bound_rule_ids: Set[str]


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------
def parse_validator_field(value: str) -> tuple[str, str]:
    """Split ``"<module>::<function>"`` into its two parts.

    Raises ``ValueError`` when the shape is wrong.
    """
    if not isinstance(value, str) or "::" not in value:
        raise ValueError(
            f"validator field {value!r} must be of form "
            f"'<module_basename>::<function_name>'"
        )
    module, _, function = value.partition("::")
    if not module or not function:
        raise ValueError(
            f"validator field {value!r} must be of form "
            f"'<module_basename>::<function_name>' (got empty module or function)"
        )
    return module, function


def infer_module_path(archetype: str, module_basename: str) -> Path:
    """Compute the absolute path of ``atdd.<archetype>.validators.<module>``.

    Raises ``ValidatorResolutionError`` when archetype is unrecognized OR
    the file does not exist.
    """
    if archetype not in _VALID_ARCHETYPES:
        raise ValidatorResolutionError(
            f"archetype {archetype!r} not in {sorted(_VALID_ARCHETYPES)!r}"
        )
    candidate = _ATDD_PKG_DIR / archetype / "validators" / f"{module_basename}.py"
    if not candidate.is_file():
        raise ValidatorResolutionError(
            f"validator module not found at {candidate}"
        )
    return candidate


def _collect_bind_rule_args(function_node: ast.FunctionDef) -> Set[str]:
    """Return the set of literal ``bind_rule("<id>")`` args inside *function_node*.

    Walks the function's full subtree (so nested calls inside helpers count)
    and recognizes both ``bind_rule(...)`` and the ``module.bind_rule(...)``
    forms. Non-literal arguments are silently ignored — the reverse
    coherence pass only checks LITERAL bindings.
    """
    bound: Set[str] = set()
    for node in ast.walk(function_node):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name: Optional[str] = None
        if isinstance(func, ast.Name):
            name = func.id
        elif isinstance(func, ast.Attribute):
            name = func.attr
        if name != "bind_rule":
            continue
        if not node.args:
            continue
        first = node.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            bound.add(first.value)
    return bound


def _collect_module_bind_rule_args(tree: ast.Module) -> Set[str]:
    """Module-level ``bind_rule(...)`` args. Resolves both literal args and the very
    common module-level string-constant indirection
    (``_RULE_ID = "..."`` ; ``_RULE = bind_rule(_RULE_ID)``)."""
    # Module-level string constants: NAME -> "literal".
    consts: dict = {}
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    consts[target.id] = node.value.value

    bound: Set[str] = set()
    for node in tree.body:
        for sub in ast.walk(node):
            if not isinstance(sub, ast.Call):
                continue
            func = sub.func
            name: Optional[str] = None
            if isinstance(func, ast.Name):
                name = func.id
            elif isinstance(func, ast.Attribute):
                name = func.attr
            if name != "bind_rule":
                continue
            if not sub.args:
                continue
            first = sub.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                bound.add(first.value)
            elif isinstance(first, ast.Name) and first.id in consts:
                bound.add(consts[first.id])
    return bound


def resolve_validator(
    *,
    archetype: str,
    validator_field: str,
) -> ResolvedValidator:
    """Resolve ``validator_field`` to a :class:`ResolvedValidator`.

    Raises ``ValidatorResolutionError`` for any of:
        * Bad ``module::function`` shape.
        * Module file missing.
        * Module file has a syntax error.
        * Function name not found at module top level.
    """
    module_basename, function_name = parse_validator_field(validator_field)
    module_path = infer_module_path(archetype, module_basename)

    try:
        source = module_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValidatorResolutionError(
            f"validator module {module_path} could not be read: {exc}"
        ) from exc

    try:
        tree = ast.parse(source, filename=str(module_path))
    except SyntaxError as exc:
        raise ValidatorResolutionError(
            f"validator module {module_path} has a syntax error at "
            f"line {exc.lineno}: {exc.msg}"
        ) from exc

    function_node: Optional[ast.FunctionDef] = None
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == function_name:
            function_node = node
            break
    if function_node is None:
        raise ValidatorResolutionError(
            f"function {function_name!r} not found at top level of "
            f"{module_path}"
        )

    bound_in_function = _collect_bind_rule_args(function_node)
    bound_at_module = _collect_module_bind_rule_args(tree)
    return ResolvedValidator(
        module_basename=module_basename,
        function_name=function_name,
        archetype=archetype,
        module_path=module_path,
        function_node=function_node,
        bound_rule_ids=bound_in_function | bound_at_module,
    )


__all__ = [
    "ResolvedValidator",
    "ValidatorResolutionError",
    "infer_module_path",
    "parse_validator_field",
    "resolve_validator",
]
