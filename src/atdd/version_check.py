"""
Version check for ATDD CLI.

Checks PyPI for newer versions and notifies users. Uses a cached check
to avoid adding latency to every command.

Cache location: ~/.atdd/version_cache.json
Disable: Set ATDD_NO_UPDATE_CHECK=1 environment variable
"""
import json
import os
import sys
import time
from pathlib import Path
from typing import Optional, Tuple
from urllib.request import urlopen
from urllib.error import URLError

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
