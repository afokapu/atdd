"""
ATDD Configuration Loader.

Loads configuration from .atdd/config.yaml for train validation and enforcement.
"""

import yaml
from pathlib import Path
from typing import Dict, Any, Optional


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
    except Exception:
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
