"""
Version check for ATDD CLI.

Two types of version checks:
1. PyPI update check - notifies when a newer version is available on PyPI
2. Repo sync check - notifies when installed version is newer than repo's last_version

Cache location: ~/.atdd/version_cache.json
Disable PyPI check: Set ATDD_NO_UPDATE_CHECK=1
Disable sync reminder: Set ATDD_NO_UPGRADE_NOTICE=1
"""
import json
import os
import sys
import time
from pathlib import Path
from typing import Optional, Tuple
from urllib.request import urlopen
from urllib.error import URLError

import yaml

from atdd import __version__

# Check once per day (86400 seconds)
CHECK_INTERVAL = 86400
CACHE_DIR = Path.home() / ".atdd"
CACHE_FILE = CACHE_DIR / "version_cache.json"
PYPI_URL = "https://pypi.org/pypi/atdd/json"


def _parse_version(version: str) -> Tuple[int, ...]:
    """Parse version string into tuple for comparison."""
    try:
        return tuple(int(x) for x in version.split(".")[:3])
    except (ValueError, AttributeError):
        return (0, 0, 0)


def _is_newer(latest: str, current: str) -> bool:
    """Check if latest version is newer than current."""
    return _parse_version(latest) > _parse_version(current)


def _load_cache() -> dict:
    """Load version cache from disk."""
    try:
        if CACHE_FILE.exists():
            with open(CACHE_FILE) as f:
                return json.load(f)
    except (json.JSONDecodeError, OSError):
        pass
    return {}


def _save_cache(data: dict) -> None:
    """Save version cache to disk."""
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        with open(CACHE_FILE, "w") as f:
            json.dump(data, f)
    except OSError:
        pass  # Silently fail if we can't write cache


def _fetch_latest_version() -> Optional[str]:
    """Fetch latest version from PyPI."""
    try:
        with urlopen(PYPI_URL, timeout=2) as response:
            data = json.loads(response.read().decode())
            return data.get("info", {}).get("version")
    except (URLError, json.JSONDecodeError, OSError, TimeoutError):
        return None


def check_for_updates() -> Optional[str]:
    """
    Check for updates if cache is stale.

    Returns:
        Message to display if update available, None otherwise.
    """
    # Respect disable flag
    if os.environ.get("ATDD_NO_UPDATE_CHECK", "").lower() in ("1", "true", "yes"):
        return None

    # Skip if running in development (version 0.0.0)
    if __version__ == "0.0.0":
        return None

    cache = _load_cache()
    now = time.time()
    last_check = cache.get("last_check", 0)
    cached_latest = cache.get("latest_version")

    # Check if cache is fresh
    if now - last_check < CHECK_INTERVAL and cached_latest:
        latest = cached_latest
    else:
        # Fetch from PyPI
        latest = _fetch_latest_version()
        if latest:
            _save_cache({
                "last_check": now,
                "latest_version": latest,
            })
        elif cached_latest:
            # Use cached version if fetch failed
            latest = cached_latest
        else:
            return None

    # Compare versions
    if latest and _is_newer(latest, __version__):
        return (
            f"\nA new version of atdd is available: {__version__} → {latest}\n"
            f"Run `pip install --upgrade atdd` to update."
        )

    return None


def print_update_notice() -> None:
    """Print update notice to stderr if available."""
    try:
        notice = check_for_updates()
        if notice:
            print(notice, file=sys.stderr)
    except Exception:
        pass  # Never fail the main command due to version check


# --- Repo sync upgrade check ---

def _load_repo_config() -> Tuple[Optional[dict], Optional[Path]]:
    """
    Load .atdd/config.yaml from current directory.

    Returns:
        Tuple of (config_dict, config_path) or (None, None) if not found.
    """
    config_path = Path.cwd() / ".atdd" / "config.yaml"
    if not config_path.exists():
        return None, None

    try:
        with open(config_path) as f:
            return yaml.safe_load(f) or {}, config_path
    except (yaml.YAMLError, OSError):
        return None, None


def _get_last_toolkit_version(config: dict) -> Optional[str]:
    """Extract toolkit.last_version from config."""
    toolkit = config.get("toolkit", {})
    return toolkit.get("last_version")


def check_upgrade_sync_needed() -> Optional[str]:
    """
    Check if repo needs sync after ATDD upgrade.

    Compares installed version vs toolkit.last_version in .atdd/config.yaml.

    Returns:
        Message to display if sync needed, None otherwise.
    """
    # Respect disable flag
    if os.environ.get("ATDD_NO_UPGRADE_NOTICE", "").lower() in ("1", "true", "yes"):
        return None

    # Skip if running in development
    if __version__ == "0.0.0":
        return None

    config, config_path = _load_repo_config()
    if config is None:
        # No .atdd/config.yaml - not an ATDD repo or not initialized
        return None

    last_version = _get_last_toolkit_version(config)
    if last_version is None:
        # First run or old config without toolkit.last_version
        # Treat as needing sync
        return f"ATDD upgraded to {__version__}. Run: atdd sync"

    # Compare versions
    if _is_newer(__version__, last_version):
        return f"ATDD upgraded ({last_version} → {__version__}). Run: atdd sync"

    return None


def update_toolkit_version(config_path: Optional[Path] = None) -> bool:
    """
    Update toolkit.last_version in .atdd/config.yaml to current installed version.

    Args:
        config_path: Path to config file. Defaults to .atdd/config.yaml in cwd.

    Returns:
        True if updated, False otherwise.
    """
    if config_path is None:
        config_path = Path.cwd() / ".atdd" / "config.yaml"

    if not config_path.exists():
        return False

    try:
        with open(config_path) as f:
            config = yaml.safe_load(f) or {}

        # Update toolkit.last_version
        if "toolkit" not in config:
            config["toolkit"] = {}
        config["toolkit"]["last_version"] = __version__

        with open(config_path, "w") as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)

        return True
    except (yaml.YAMLError, OSError):
        return False


def print_upgrade_sync_notice() -> None:
    """Print upgrade sync notice to stderr if needed."""
    try:
        notice = check_upgrade_sync_needed()
        if notice:
            print(f"\n⚠️  {notice}\n", file=sys.stderr)
    except Exception:
        pass  # Never fail the main command
