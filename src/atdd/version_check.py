"""
Version check for ATDD CLI.

Two types of version checks:
1. PyPI update check - notifies when a newer version is available on PyPI
2. Repo sync check - notifies when installed version is newer than repo's last_version

Cache location: ~/.atdd/version_cache.json
Disable PyPI check: CI=true ATDD_NO_UPDATE_CHECK=1 (CI only)
Disable sync reminder: CI=true ATDD_NO_UPGRADE_NOTICE=1 (CI only)
"""
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Optional, Tuple
from urllib.request import Request, urlopen
from urllib.error import URLError

import yaml

from atdd import __version__

logger = logging.getLogger(__name__)

# Version-specific upgrade notes shown to consumers after upgrade.
# Key = version, value = short human-readable note.
# Only versions with notable changes need entries.
UPGRADE_NOTES: dict = {
    "1.15.0": "SMOKE phase added between GREEN and REFACTOR",
    "1.16.0": "Self-compliance: toolkit validates itself. New: find_python_dir(), substring class matching",
    "1.16.1": "New: init.skip_workflows config flag prevents workflow overwrite",
    "1.16.2": "Fixed: contract path-to-URN conversion, WMBT acceptances, 14 Phase 2 warnings resolved",
    "1.16.3": "Fixed: kebab-case contract $id now normalizes correctly to PascalCase",
    "1.16.4": "New: publish workflow auto-generates GitHub Release notes. Run atdd init to update consumer workflow",
}

# Check once per day (86400 seconds)
CHECK_INTERVAL = 86400
CACHE_DIR = Path.home() / ".atdd"
CACHE_FILE = CACHE_DIR / "version_cache.json"
PYPI_URL = "https://pypi.org/pypi/atdd/json"


def _read_direct_url() -> Optional[dict]:
    """Return parsed direct_url.json for the 'atdd' distribution, or None."""
    try:
        import importlib.metadata as meta
        raw = meta.distribution("atdd").read_text("direct_url.json")
        if raw:
            import json as _json
            return _json.loads(raw)
    except Exception:  # atdd:suppress(coder.logging.coach-silent-swallow)
        pass
    return None


def _is_editable_install() -> bool:
    """Return True if atdd is installed as an editable (dev) install."""
    data = _read_direct_url()
    if data:
        return bool(data.get("dir_info", {}).get("editable", False))
    return False


def detect_install_method() -> str:
    """Detect how atdd was installed: 'pipx', 'editable', 'pip', or 'unknown'.

    Detection order:
    1. pipx — sys.executable path contains '/pipx/venvs/'
    2. editable — direct_url.json has dir_info.editable=true
    3. pip — fallback for all other cases
    """
    exe = sys.executable
    if "/pipx/venvs/" in exe or "\\pipx\\venvs\\" in exe:
        return "pipx"
    if _is_editable_install():
        return "editable"
    return "pip"


def upgrade_command() -> str:
    """Return the correct upgrade command string for the detected install method."""
    method = detect_install_method()
    if method == "pipx":
        return "pipx upgrade atdd"
    if method == "editable":
        data = _read_direct_url()
        if data:
            url = data.get("url", "")
            if url.startswith("file://"):
                return f"git -C {url[len('file://'):]} pull"
        return "git pull  # (in your atdd source checkout)"
    return "pip install --upgrade atdd"


def _parse_version(version: str) -> Tuple[int, ...]:
    """Parse version string into tuple for comparison."""
    try:
        return tuple(int(x) for x in version.split(".")[:3])
    except (ValueError, AttributeError):  # atdd:suppress(coder.logging.coach-silent-swallow)
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
    except (json.JSONDecodeError, OSError):  # atdd:suppress(coder.logging.coach-silent-swallow)
        pass
    return {}


def _save_cache(data: dict) -> None:
    """Save version cache to disk."""
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        with open(CACHE_FILE, "w") as f:
            json.dump(data, f)
    except OSError:  # atdd:suppress(coder.logging.coach-silent-swallow)
        pass  # Silently fail if we can't write cache


def _fetch_latest_version() -> Optional[str]:
    """Fetch latest version from PyPI.

    Sends ``Cache-Control: no-cache`` to defeat any future PyPI/CDN caching
    of the JSON metadata endpoint — belt-and-braces against the propagation
    window observed during fresh-tag publishes.
    """
    try:
        request = Request(PYPI_URL, headers={"Cache-Control": "no-cache"})
        with urlopen(request, timeout=2) as response:
            data = json.loads(response.read().decode())
            return data.get("info", {}).get("version")
    except (URLError, json.JSONDecodeError, OSError, TimeoutError):  # atdd:suppress(coder.logging.coach-silent-swallow)
        return None


def check_for_updates() -> Optional[str]:
    """
    Check for updates if cache is stale.

    Returns:
        Message to display if update available, None otherwise.
    """
    # Respect disable flag (CI only)
    if os.environ.get("CI") == "true" and os.environ.get("ATDD_NO_UPDATE_CHECK", "").lower() in ("1", "true", "yes"):
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
            f"Run `{upgrade_command()}` to update."
        )

    return None


def print_update_notice() -> None:
    """Print update notice to stderr if available."""
    try:
        notice = check_for_updates()
        if notice:
            print(notice, file=sys.stderr)
    except Exception:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-31
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
    except (yaml.YAMLError, OSError):  # atdd:suppress(coder.logging.coach-silent-swallow)
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
    # Respect disable flag (CI only)
    if os.environ.get("CI") == "true" and os.environ.get("ATDD_NO_UPGRADE_NOTICE", "").lower() in ("1", "true", "yes"):
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
        return f"ATDD upgraded to {__version__}. Run: atdd sync && atdd init"

    # Compare versions
    if _is_newer(__version__, last_version):
        notes = get_upgrade_notes(last_version, __version__)
        msg = f"ATDD upgraded ({last_version} → {__version__}). Run: atdd sync && atdd init"
        if notes:
            msg += "\n" + "\n".join(f"  → {v}: {note}" for v, note in notes)
        return msg

    return None


def get_upgrade_notes(from_version: str, to_version: str) -> list:
    """Get upgrade notes for versions between from_version and to_version.

    Returns:
        List of (version, note) tuples for versions in range.
    """
    from_tuple = _parse_version(from_version)
    to_tuple = _parse_version(to_version)
    notes = []
    for version, note in sorted(UPGRADE_NOTES.items(), key=lambda x: _parse_version(x[0]), reverse=True):
        v_tuple = _parse_version(version)
        if from_tuple < v_tuple <= to_tuple:
            notes.append((version, note))
    return notes


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
    except (yaml.YAMLError, OSError):  # atdd:suppress(coder.logging.coach-silent-swallow)
        return False


def print_upgrade_sync_notice() -> None:
    """Print a warning when the installed toolkit version is ahead of the repo.

    Read-only: the upgrade banner is printed to stderr, but no files are
    written. Users (or agents) must opt in to the sync explicitly by running
    ``atdd sync`` (which is the canonical writer of ``toolkit.last_version``
    and the agent config files).

    Issue #342: the previous implementation also auto-ran
    ``AgentConfigSync().sync()`` and ``update_toolkit_version()`` here,
    which mutated ``.atdd/config.yaml`` and the agent configs on every CLI
    invocation — including ``atdd --help``. That violated the contract that
    read-only commands leave the working tree clean. The warning is the
    useful part; the write was the bug.
    """
    try:
        notice = check_upgrade_sync_needed()
        if notice:
            print(f"\n⚠️  {notice}", file=sys.stderr)
            print(file=sys.stderr)
    except Exception:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-31
        pass  # Never fail the main command


# --- Version gate (git hook enforcement) ---

_SEMVER_RE = re.compile(r"(\d+\.\d+\.\d+)")

# The `atdd --version` probe must be immune to the caller's environment. The
# pre-push hook exports PYTHONPATH=<repo>/src so that `atdd validate` runs the
# working tree's code; if that leaked into this probe, a console script whose
# shebang lacks `-E` would import the tree's `atdd` and resolve
# `importlib.metadata.version("atdd")` against `src/atdd.egg-info/PKG-INFO` —
# the very ghost the gate exists to ignore. Scrub it, and run from a neutral
# cwd so no source tree is on the path at all.
_PROBE_SILENCE = {"CI": "true", "ATDD_NO_UPDATE_CHECK": "1", "ATDD_NO_UPGRADE_NOTICE": "1"}


def installed_cli_version() -> Optional[str]:
    """Return the version of the ``atdd`` CLI on PATH — the one the operator runs.

    The gate means to ask "is the CLI you are running outdated?". It must not ask
    the working tree: ``atdd/__init__.py`` resolves
    ``importlib.metadata.version("atdd")``, which in a source checkout picks up
    ``src/atdd.egg-info/PKG-INFO`` — a gitignored build artifact that any
    ``pip install -e .`` (CI does this) leaves frozen at an ancient version.
    Worktrees were measured carrying ghosts from 3.112.0 to 4.1.1 (#1449).

    Returns:
        The semver string reported by the executable, or None when it cannot be
        determined (no ``atdd`` on PATH, probe failure, unparseable output).
        Callers MUST treat None as "unknowable" and fail open — never block a
        push on a version we could not establish.
    """
    exe = shutil.which("atdd")
    if not exe:
        return None

    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env.update(_PROBE_SILENCE)

    try:
        result = subprocess.run(
            [exe, "--version"],
            capture_output=True, text=True, timeout=10,
            env=env, cwd=tempfile.gettempdir(),
        )
    except Exception:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-31
        return None

    if result.returncode != 0:
        return None

    match = _SEMVER_RE.search(result.stdout or "")
    return match.group(1) if match else None


def _gate_version() -> Optional[str]:
    """The version the push gate judges, or None when it is unknowable.

    None means fail OPEN. A dev/editable install legitimately reports 0.0.0
    (#1172 makes the tree version dynamic and store-projected), and there is
    nothing to compare it against.
    """
    current = installed_cli_version()
    if not current or current == "0.0.0":
        return None
    return current


def is_outdated() -> Tuple[bool, str, str]:
    """Check if the INSTALLED atdd CLI is outdated vs PyPI (no cache).

    Judges the ``atdd`` executable on PATH, never the working tree (#1449).

    Returns:
        Tuple of (outdated, current_version, latest_version).
        If the installed version is unknowable, returns (False, "", "") — open.
        If PyPI is unreachable, returns (False, current, "").
    """
    current = _gate_version()
    if current is None:
        return False, "", ""

    latest = _fetch_latest_version()
    if latest is None:
        return False, current, ""

    return _is_newer(latest, current), current, latest


def _is_pep668_error(stderr: str) -> bool:
    """Detect PEP 668 externally-managed-environment refusal.

    Triggered on macOS Homebrew Python and Debian/Ubuntu system Python where
    pip refuses to install into the system site-packages without an explicit
    --break-system-packages override.
    """
    return "externally-managed-environment" in stderr or "error: externally-managed" in stderr


def _verify_installed_version(expected: Optional[str]) -> bool:
    """Verify the on-disk installed atdd version matches ``expected``.

    Spawns a fresh subprocess to read ``importlib.metadata.version("atdd")``.
    A subprocess is required because ``importlib.metadata`` caches its
    distribution-finder state at module-import time; after ``pip install``
    mutates ``site-packages``, ``importlib.reload(atdd)`` re-runs
    ``__init__.py`` but the in-process metadata cache still serves the
    pre-install version. A fresh interpreter starts with no cache and reads
    the actual on-disk ``*.dist-info/`` directory.

    Returns:
        True iff ``expected`` is None (no target → no check) or the spawned
        subprocess reports the same version. False on subprocess failure,
        timeout, or version mismatch.
    """
    if not expected:
        return True

    import subprocess as _sp

    try:
        result = _sp.run(
            [sys.executable, "-c",
             "import importlib.metadata; print(importlib.metadata.version('atdd'))"],
            capture_output=True, text=True, timeout=10,
        )
    except _sp.TimeoutExpired:
        logger.debug(
            "auto_upgrade verify: subprocess timed out after 10s",
            extra={"phase": "verify", "outcome": "timeout", "timeout_s": 10},
        )
        return False
    except Exception:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-31
        return False

    if result.returncode != 0:
        return False
    installed = result.stdout.strip()
    return installed == expected


def _run_with_pep668_retry(cmd: list, *, timeout: int = 120) -> Tuple[bool, str]:
    """Run a pip command, retrying once with ``--break-system-packages`` on PEP 668 refusal.

    Returns (success, stderr_of_last_attempt).
    """
    import subprocess as _sp

    result = _sp.run(cmd, capture_output=True, text=True, timeout=timeout)
    if result.returncode == 0:
        return True, result.stderr
    if _is_pep668_error(result.stderr):
        logger.debug(
            "PEP 668 refusal detected; retrying with --break-system-packages",
            extra={"phase": "pip-install", "mechanism": "pep668-fallback"},
        )
        retry = _sp.run(
            cmd + ["--break-system-packages"],
            capture_output=True, text=True, timeout=timeout,
        )
        return retry.returncode == 0, retry.stderr
    return False, result.stderr


def auto_upgrade() -> bool:
    """Run pip install --upgrade atdd. Returns True on success.

    Two-attempt strategy to handle PyPI's CDN propagation window after a
    fresh tag publish:

    1. **Attempt 1** — name-only resolution: ``pip install --upgrade
       --no-cache-dir atdd``. ``--no-cache-dir`` busts pip's local wheel
       cache (belt-and-braces). On returncode 0, verify the installed
       version matches what ``_fetch_latest_version`` reported.
    2. **Attempt 2** — explicit version pin: if Attempt 1 succeeded but
       verify failed (pip's resolver served a stale "latest" from its
       in-process metadata cache), retry with
       ``pip install --upgrade --no-cache-dir atdd==<expected>``. The
       version pin forces fresh resolution and is the load-bearing fix.

    Each attempt retries with ``--break-system-packages`` on PEP 668
    refusal (Homebrew/Debian-managed Pythons).
    """
    target = _fetch_latest_version()
    base_cmd = [sys.executable, "-m", "pip", "install", "--upgrade", "--no-cache-dir", "atdd"]

    try:
        logger.debug(
            "auto_upgrade attempt %d: cmd=%s", 1, base_cmd,
            extra={"phase": "pip-install", "attempt": 1, "cmd": base_cmd, "target": target},
        )
        ok, _stderr = _run_with_pep668_retry(base_cmd)
        if ok and _verify_installed_version(target):
            logger.debug(
                "upgrade verified: atdd %s installed", target,
                extra={"phase": "verify", "attempt": 1, "version": target, "outcome": "match"},
            )
            return True
        if ok and target:
            logger.debug(
                "pip install returncode=0 but installed != expected=%s; retrying with explicit pin",
                target,
                extra={"phase": "verify", "attempt": 1, "expected": target, "outcome": "mismatch"},
            )
        if not ok and not target:
            return False

        if target:
            pinned_cmd = [
                sys.executable, "-m", "pip", "install",
                "--upgrade", "--no-cache-dir", f"atdd=={target}",
            ]
            logger.debug(
                "auto_upgrade attempt %d (pinned): cmd=%s", 2, pinned_cmd,
                extra={"phase": "pip-install", "attempt": 2, "cmd": pinned_cmd, "target": target},
            )
            ok2, _stderr2 = _run_with_pep668_retry(pinned_cmd)
            if ok2 and _verify_installed_version(target):
                logger.debug(
                    "upgrade verified after pin: atdd %s installed", target,
                    extra={"phase": "verify", "attempt": 2, "version": target, "outcome": "match"},
                )
                return True
            return False

        return False
    except Exception:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-31
        return False


def _gate_main(minimum_version: Optional[str] = None) -> None:
    """CLI entry point for version-gate hook.

    Gate only — never runs pip install or auto_upgrade().
    Exit 0 = allow push, exit 1 = block push (atdd is outdated).

    When minimum_version is provided (or read from .atdd/config.yaml under
    release.minimum_version), the gate compares installed vs that floor rather
    than PyPI latest. This prevents a patch release made seconds ago from
    blocking the operator who authored it.
    """
    if minimum_version is None:
        config, _ = _load_repo_config()
        if config:
            release_cfg = config.get("release", {}) or {}
            minimum_version = (
                release_cfg.get("minimum_version")
                or config.get("minimum_version")
                or (config.get("toolkit", {}) or {}).get("minimum_version")
            )

    if minimum_version is not None:
        current = _gate_version()
        if current is None:
            # Unknowable installed version (dev install / no atdd on PATH) —
            # fail OPEN. Never block a push on a version we could not establish.
            return
        if _parse_version(current) >= _parse_version(minimum_version):
            print(f"atdd {current} meets minimum_version {minimum_version}")
            return
        print(
            f"atdd {current} is below minimum_version {minimum_version}.\n"
            f"Run `atdd upgrade` then retry your git operation.",
            file=sys.stderr,
        )
        sys.exit(1)
        return

    outdated, current, latest = is_outdated()

    if not outdated:
        if not current:
            print("WARNING: Could not determine the installed atdd version "
                  "— skipping version gate", file=sys.stderr)
        elif not latest:
            print(f"WARNING: Could not reach PyPI — skipping version gate (atdd {current})",
                  file=sys.stderr)
        else:
            print(f"atdd {current} is up to date")
        return  # exit 0

    print(
        f"atdd {current} is outdated (latest: {latest}).\n"
        f"Run `atdd upgrade` then retry your git operation.",
        file=sys.stderr,
    )
    sys.exit(1)


def should_emit_upgrade_banner(current_version: str, marker_dir) -> bool:
    """Return True when the upgrade banner should be shown.

    Returns False when a ``sync_acknowledged_{current_version}`` marker exists,
    meaning the operator has already run ``atdd sync`` for this version.
    Returns True when no marker exists or when the marker is for an older version.

    Issue #812 / Y002.
    """
    from pathlib import Path as _Path

    marker = _Path(marker_dir) / f"sync_acknowledged_{current_version}"
    return not marker.exists()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--gate", action="store_true", help="Version gate check")
    args = parser.parse_args()

    if args.gate:
        _gate_main()
    else:
        print_update_notice()
