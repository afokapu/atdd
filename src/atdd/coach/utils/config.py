"""
ATDD Configuration Loader.

Loads configuration from .atdd/config.yaml for train validation and enforcement.
"""

import yaml
from pathlib import Path
from typing import Dict, Any, Optional


DEFAULT_CODE_ROOTS: Dict[str, str] = {
    "python": "python",
    "supabase": "supabase/functions",
    "web": "web/src",
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
    except Exception:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-31
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
