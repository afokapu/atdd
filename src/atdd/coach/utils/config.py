"""
ATDD Configuration Loader.

Loads configuration from .atdd/config.yaml for train validation and enforcement.
"""

import logging
import yaml
from pathlib import Path
from typing import Dict, Any, Optional


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Stack layout defaults (coach.graph.implementation-root-resolution)
#
# These two maps are the ONLY place in core that names a concrete stack path.
# Validators must never re-derive them: they call resolve_code_root() /
# resolve_stack_container() and skip the stack when the resolver returns None.
#
# They are also the designated relocation target for #1121 — the *invariant*
# (config-driven resolution) stays core; these *defaults* move to
# atdd.workspace.python-pytest. Keeping them in one module is what makes that
# move a lift rather than a 57-file re-sweep.
# ---------------------------------------------------------------------------

# Where a stack's source code lives — what an implementation resolver walks.
DEFAULT_CODE_ROOTS: Dict[str, str] = {
    "python": "python",
    "supabase": "supabase/functions",
    "web": "web/src",
}

# Where a stack's *project* lives — the directory holding its manifests and
# sibling trees (package.json, tsconfig.json, tests/, migrations/). Distinct
# from the code root: web code sits in `web/src`, but `tsconfig.json` sits in
# `web/`. For python the two coincide; that is a property of the layout, not a
# rule, so it is declared rather than derived.
DEFAULT_STACK_CONTAINERS: Dict[str, str] = {
    "python": "python",
    "supabase": "supabase",
    "web": "web",
}

# A stack's entrypoint ("root app"), relative to its code root — the station
# master for python. A root app is a starting point of a path just as much as a
# root directory is, so it is declared rather than frozen into validator source:
# a consumer whose backend entrypoint is `main.py` or `server/asgi.py` should not
# have to fork a validator to say so.
DEFAULT_STACK_ENTRYPOINTS: Dict[str, str] = {
    "python": "app.py",
}


def get_code_roots(config: Optional[Dict[str, Any]]) -> Dict[str, Path]:
    """
    Resolve the declared implementation-root map from an ATDD config dict.

    Merges the built-in defaults (``python``, ``supabase``, ``web``) with
    any overrides under the optional ``code:`` key. Unknown stack names
    (e.g. ``rust``, ``go``) are preserved verbatim so consumers can declare
    future stacks before resolvers exist — the validator is responsible for
    skipping keys it has no resolver for (Decision #2).

    The ``toolkit`` key is intentionally NOT in the defaults (Decision #1):
    consumer repos that vendor or fork the atdd toolkit would otherwise
    index the vendored copy as their own implementation. Toolkit roots
    must be opted into by setting ``code.toolkit`` explicitly.

    Args:
        config: Parsed ``.atdd/config.yaml`` dict. None / missing / malformed
                ``code`` blocks fall back to defaults.

    Returns:
        Dict[str, Path] mapping stack-name → Path (relative to repo root).
    """
    if not isinstance(config, dict):
        overrides: Dict[str, Any] = {}
    else:
        overrides = config.get("code") or {}
        if not isinstance(overrides, dict):
            overrides = {}

    merged: Dict[str, Path] = {k: Path(v) for k, v in DEFAULT_CODE_ROOTS.items()}
    for key, value in overrides.items():
        merged[key] = Path(value)
    return merged


def get_stack_containers(config: Optional[Dict[str, Any]]) -> Dict[str, Path]:
    """
    Resolve the declared stack-container map from an ATDD config dict.

    A *container* is the stack's project directory — where its manifests
    (``package.json``, ``tsconfig.json``) and sibling trees (``tests/``,
    ``migrations/``) sit. It is not derivable from the code root: ``web/src``
    implies a ``web`` container, but ``apps/frontend/src`` does not imply
    ``apps``. So it is declared, under the optional ``stack_containers:`` key,
    and merged over :data:`DEFAULT_STACK_CONTAINERS`.

    Same skip-unknown contract as :func:`get_code_roots`: keys with no
    resolver are preserved verbatim, and callers skip what they cannot handle.
    """
    if not isinstance(config, dict):
        overrides: Dict[str, Any] = {}
    else:
        overrides = config.get("stack_containers") or {}
        if not isinstance(overrides, dict):
            overrides = {}

    merged: Dict[str, Path] = {
        k: Path(v) for k, v in DEFAULT_STACK_CONTAINERS.items()
    }
    for key, value in overrides.items():
        merged[key] = Path(value)
    return merged


def get_stack_entrypoints(config: Optional[Dict[str, Any]]) -> Dict[str, Path]:
    """Resolve the declared stack-entrypoint map (relative to each code root)."""
    if not isinstance(config, dict):
        overrides: Dict[str, Any] = {}
    else:
        overrides = config.get("stack_entrypoints") or {}
        if not isinstance(overrides, dict):
            overrides = {}

    merged: Dict[str, Path] = {
        k: Path(v) for k, v in DEFAULT_STACK_ENTRYPOINTS.items()
    }
    for key, value in overrides.items():
        merged[key] = Path(value)
    return merged


_TABLES = {
    "code root": get_code_roots,
    "container": get_stack_containers,
}


def _resolve(
    which: str,
    stack: str,
    repo_root: Path,
    config: Optional[Dict[str, Any]],
) -> Optional[Path]:
    """Shared body for the two public root resolvers."""
    if config is None:
        config = load_atdd_config(repo_root)
    table = _TABLES[which](config)
    relative = table.get(stack)
    if relative is None:
        # Decision #2: an undeclared stack is skipped, never a crash. A consumer
        # may name `rust`/`go`/`dart` in config long before a resolver ships,
        # and a consumer with no web tier must not fail the web validators.
        logger.debug(
            "no %s declared for stack %r; skipping (declare it under "
            ".atdd/config.yaml to enable)",
            which,
            stack,
            extra={"stack": stack, "root_kind": which},
        )
        return None
    return repo_root / relative


def resolve_code_root(
    stack: str,
    repo_root: Path,
    config: Optional[Dict[str, Any]] = None,
) -> Optional[Path]:
    """
    Absolute path to *stack*'s code root, or ``None`` if it is not declared.

    This is the single seam validators use instead of hardcoding
    ``REPO_ROOT / "python"``. Returning ``None`` (rather than a path that does
    not exist) lets a caller distinguish "this repo has no such stack" from
    "the stack is declared but its directory is missing" — the two want
    different skip messages.
    """
    return _resolve("code root", stack, repo_root, config)


def resolve_stack_container(
    stack: str,
    repo_root: Path,
    config: Optional[Dict[str, Any]] = None,
) -> Optional[Path]:
    """
    Absolute path to *stack*'s project container, or ``None`` if not declared.

    Use this for stack-level artifacts that sit beside the code root rather
    than inside it — ``web/tsconfig.json``, ``web/tests``,
    ``supabase/migrations``. Use :func:`resolve_code_root` for source scans.
    """
    return _resolve("container", stack, repo_root, config)


def resolve_stack_entrypoint(
    stack: str,
    repo_root: Path,
    config: Optional[Dict[str, Any]] = None,
) -> Optional[Path]:
    """
    Absolute path to *stack*'s entrypoint file, or ``None`` if not resolvable.

    Returns ``None`` when the stack has no declared code root or no declared
    entrypoint — a repo may have a python tier with no station master, and that
    is a fact to skip on, not to crash on (it is precisely what #689 got wrong:
    the guard checked that the python root existed, then the tests reached for
    an ``app.py`` that was never there).
    """
    if config is None:
        config = load_atdd_config(repo_root)
    root = resolve_code_root(stack, repo_root, config)
    if root is None:
        return None
    entrypoint = get_stack_entrypoints(config).get(stack)
    if entrypoint is None:
        logger.debug(
            "no entrypoint declared for stack %r; skipping",
            stack,
            extra={"stack": stack},
        )
        return None
    return root / entrypoint


def load_atdd_config(repo_root: Path) -> Dict[str, Any]:
    """
    Load .atdd/config.yaml configuration file.

    The config file controls:
    - FastAPI template enforcement (Section 11)
    - Train validation behavior
    - Custom path conventions

    Args:
        repo_root: Repository root path

    Returns:
        Parsed configuration dict, or empty dict if file doesn't exist

    Example config:
        trains:
          enforce_fastapi_template: true
          backend_runner_paths:
            - python/trains/runner.py
            - python/trains/{train_id}/runner.py
          frontend_allowed_roots:
            - web/src/
            - web/components/
    """
    config_path = repo_root / ".atdd" / "config.yaml"

    if not config_path.exists():
        return {}

    try:
        with open(config_path) as f:
            config = yaml.safe_load(f)
            return config if config else {}
    except Exception:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-12-06
        return {}


def get_train_config(repo_root: Path) -> Dict[str, Any]:
    """
    Get train-specific configuration.

    Args:
        repo_root: Repository root path

    Returns:
        Train configuration dict with defaults applied
    """
    config = load_atdd_config(repo_root)
    train_config = config.get("trains", {})

    # Apply defaults
    defaults = {
        "enforce_fastapi_template": False,
        "backend_runner_paths": [
            "python/trains/runner.py",
            "python/trains/{train_id}/runner.py"
        ],
        "frontend_allowed_roots": [
            "web/src/",
            "web/components/",
            "web/pages/"
        ],
        "frontend_python_paths": [
            "python/streamlit/",
            "python/apps/"
        ],
        "e2e_backend_pattern": "e2e/{theme}/test_{train_id}*.py",
        "e2e_frontend_pattern": "web/e2e/{train_id}/*.spec.ts"
    }

    # Merge with defaults
    for key, default_value in defaults.items():
        if key not in train_config:
            train_config[key] = default_value

    return train_config


def get_validation_config(repo_root: Path) -> Dict[str, Any]:
    """
    Get validation-specific configuration.

    Args:
        repo_root: Repository root path

    Returns:
        Validation configuration with defaults
    """
    config = load_atdd_config(repo_root)
    validation_config = config.get("validation", {})

    defaults = {
        "strict_mode": False,
        "warn_on_missing_tests": True,
        "warn_on_missing_code": True,
        "require_primary_wagon": False
    }

    for key, default_value in defaults.items():
        if key not in validation_config:
            validation_config[key] = default_value

    return validation_config


def get_train_runner_config(repo_root: Path) -> Dict[str, Any]:
    """Get the TrainRunner configuration (docs/coach-decomposition.md §7.4).

    Reads the reserved ``train:`` block of ``.atdd/config.yaml``. Only the
    ``jsonl`` runner is implemented in Child 8 (#895); ``temporal``/``langgraph``
    are reserved names (§7.2/§7.3). Defaults are applied when the block — or the
    whole file — is absent.

    Returns:
        Dict with at least ``runner`` (default ``"jsonl"``) and the reserved
        ``concurrency`` / ``resume`` / ``conventions`` sub-blocks.
    """
    config = load_atdd_config(repo_root)
    train_config = config.get("train", {})
    if not isinstance(train_config, dict):
        train_config = {}

    defaults = {
        "runner": "jsonl",
        "concurrency": {"max_parallel_issues": 4},
        "resume": {"auto_resume_on_start": False},
        "conventions": {"snapshot_on_run_start": True},
    }
    for key, default_value in defaults.items():
        if key not in train_config:
            train_config[key] = default_value

    return train_config


def is_feature_enabled(repo_root: Path, feature: str) -> bool:
    """
    Check if a specific feature is enabled in config.

    Args:
        repo_root: Repository root path
        feature: Feature name to check

    Returns:
        True if feature is enabled, False otherwise
    """
    config = load_atdd_config(repo_root)
    features = config.get("features", {})
    return features.get(feature, False)
