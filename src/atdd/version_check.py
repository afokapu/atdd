"""
Version check for ATDD CLI.

Two types of version checks:
1. PyPI update check - notifies when a newer version is available on PyPI
2. Repo sync check - notifies when the installed version is newer than the
   version this checkout was last synced against

The two checks use different, deliberately separate storage:

- PyPI check  → ``~/.atdd/version_cache.json`` (per-user, a cache)
- Sync check  → ``<repo>/.atdd/runtime/toolkit-sync.json`` (per-checkout, a
  record). Untracked by design (#1641): its predecessor lived in the
  git-tracked ``.atdd/config.yaml`` and was reverted by every branch switch.

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


def _resolve_latest_version(cache: dict, now: float) -> Optional[str]:
    """The latest published version to compare against.

    The cached value while the cache is fresh; otherwise a PyPI fetch, falling
    back to the stale cached value when that fetch fails. None when neither
    source yields a version.
    """
    cached_latest = cache.get("latest_version")
    last_check = cache.get("last_check", 0)
    if now - last_check < CHECK_INTERVAL and cached_latest:
        return cached_latest

    latest = _fetch_latest_version()
    if latest:
        _save_cache({
            "last_check": now,
            "latest_version": latest,
        })
        return latest
    return cached_latest


def check_for_updates() -> Optional[str]:
    """
    Check for updates when the cache is stale.

    Returns:
        Message to display if update available, None otherwise.
    """
    # Respect disable flag (CI only)
    if os.environ.get("CI") == "true" and os.environ.get("ATDD_NO_UPDATE_CHECK", "").lower() in ("1", "true", "yes"):
        return None

    # Skip when running in development (version 0.0.0)
    if __version__ == "0.0.0":
        return None

    latest = _resolve_latest_version(_load_cache(), time.time())
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
    """Extract toolkit.last_version from config.

    Read-only legacy accessor: the field is the pre-#1641 storage location and
    is consulted exactly once, by :func:`_adopt_legacy_last_version`, to seed the
    untracked record. Nothing writes it any more.
    """
    toolkit = config.get("toolkit", {})
    return toolkit.get("last_version")


def _sync_record_path(root: Optional[Path] = None) -> Path:
    """Path to this checkout's toolkit-sync record."""
    return (root or Path.cwd()) / ".atdd" / "runtime" / "toolkit-sync.json"


def _read_sync_record(root: Optional[Path] = None) -> Optional[str]:
    """The toolkit version this checkout was last synced against, or None.

    Absence is normal (never synced, or a checkout predating #1641) and is not
    an error — callers treat None as "fall back to the legacy field".
    """
    try:
        with open(_sync_record_path(root)) as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):  # atdd:suppress(coder.logging.coach-silent-swallow)
        return None
    if not isinstance(data, dict):
        return None
    version = data.get("last_synced_version")
    return str(version) if version else None


def record_toolkit_sync(root: Optional[Path] = None, version: Optional[str] = None) -> bool:
    """Record ``version`` (default: the installed version) as this checkout's
    last synced toolkit version.

    Replaces the pre-#1641 ``update_toolkit_version``, which wrote
    ``toolkit.last_version`` into the **git-tracked** ``.atdd/config.yaml``. That
    write was correct but ephemeral: an uncommitted edit to a tracked file, so
    every ``git checkout``/``stash``/``reset`` reverted it and every fresh
    worktree started without it. The banner therefore reported the last
    *committed* value — frozen at 3.106.0 since 87319e16 — on every invocation.

    ``.atdd/runtime/`` is already gitignored, so the record is per-checkout and
    survives branch switches. It is deliberately NOT ``.atdd/cache/``: a cache
    is regenerable and may legitimately be cleaned, which would resurrect the
    banner.

    Guarded on ``.atdd/`` already existing: ``atdd sync`` is a refresher, not an
    installer, and must not conjure an ``.atdd/`` tree in a repo that never ran
    ``atdd init``. The predecessor got this for free by requiring an existing
    ``config.yaml``; writing into a fresh subdirectory does not, so the check is
    explicit here.

    Returns:
        True when the record was written, False when this is not an initialized
        ATDD repo or on any I/O failure. Callers must not treat False as fatal —
        failing to record only means the banner fires again next invocation.
    """
    path = _sync_record_path(root)
    if not path.parent.parent.is_dir():
        return False
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(
                {"last_synced_version": version or __version__, "synced_at": int(time.time())},
                f,
            )
        return True
    except OSError as exc:
        logger.debug(
            "record_toolkit_sync: could not write the toolkit-sync record",
            extra={
                "phase": "sync",
                "outcome": "write_failed",
                "path": str(path),
                "error": str(exc),
            },
        )
        return False


def _legacy_last_version(config: dict) -> Optional[str]:
    """The pre-#1641 ``toolkit.last_version``, read only.

    Deliberately does NOT write the untracked record. ``check_upgrade_sync_needed``
    runs on every CLI invocation, including ``atdd --help``, and #342 established
    that the check must not write anything — adopting the legacy value here would
    re-introduce a write on the read path.

    Migration therefore happens on the next ``atdd sync``, which is the command
    the banner tells the operator to run and the only writer of the record. Cost
    of the pure read: an unsynced repo sees one more banner carrying the stale
    legacy from-version, and it is correct from then on.
    """
    last_version = _get_last_toolkit_version(config)
    return str(last_version) if last_version else None


def _upgrade_sync_message(last_version: str) -> Optional[str]:
    """The sync notice for an upgrade away from ``last_version``, with any
    upgrade notes appended. None when the installed version is not newer."""
    if not _is_newer(__version__, last_version):
        return None
    msg = f"ATDD upgraded ({last_version} → {__version__}). Run: atdd sync && atdd init"
    notes = get_upgrade_notes(last_version, __version__)
    if notes:
        msg += "\n" + "\n".join(f"  → {v}: {note}" for v, note in notes)
    return msg


def _upgrade_notice_silenced() -> bool:
    """Whether the banner must stay silent regardless of any recorded version.

    Two unconditional mutes: the CI opt-out, and a development checkout, where
    ``__version__`` is the ``0.0.0`` sentinel and no comparison is meaningful.
    """
    if os.environ.get("CI") == "true" and os.environ.get("ATDD_NO_UPGRADE_NOTICE", "").lower() in ("1", "true", "yes"):
        return True
    return __version__ == "0.0.0"


def check_upgrade_sync_needed() -> Optional[str]:
    """
    Check whether this checkout needs sync after an ATDD upgrade.

    Compares the installed version against the version recorded in
    ``.atdd/runtime/toolkit-sync.json`` (see :func:`record_toolkit_sync`),
    falling back once to the legacy ``toolkit.last_version`` field.

    Returns:
        Message to display if sync needed, None otherwise.
    """
    if _upgrade_notice_silenced():
        return None

    # Fast path, deliberately FIRST. This function runs on every single CLI
    # invocation; the record is one stat plus a ~60-byte json.load. When it
    # already names the installed version — the overwhelmingly common case —
    # return before touching config.yaml, so a pure-Python yaml.safe_load of
    # the whole config never happens on the hot path.
    recorded = _read_sync_record()
    if recorded == __version__:
        return None

    if recorded is None:
        config, _config_path = _load_repo_config()
        if config is None:
            # No .atdd/config.yaml — not an ATDD repo or not initialized.
            # Stay silent, exactly as before #1641.
            return None
        recorded = _legacy_last_version(config)
        if recorded is None:
            # An ATDD repo that has never recorded a sync (fresh init, or a
            # config predating the legacy field). Treat as needing sync — but
            # with no credible from-version, do not invent one.
            return f"ATDD upgraded to {__version__}. Run: atdd sync && atdd init"

    return _upgrade_sync_message(recorded)


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


def print_upgrade_sync_notice() -> None:
    """Print a warning when the installed toolkit version is ahead of the repo.

    Read-only: the upgrade banner is printed to stderr, but no files are
    written. Users (or agents) must opt in to the sync explicitly by running
    ``atdd sync`` (the canonical writer of the toolkit-sync record and the
    agent config files).

    Issue #342: the previous implementation also auto-ran
    ``AgentConfigSync().sync()`` and the version stamp here, which mutated
    ``.atdd/config.yaml`` and the agent configs on every CLI invocation —
    including ``atdd --help``. That violated the contract that read-only
    commands leave the working tree clean. The warning is the useful part;
    the write was the bug. #1641 preserves that invariant: the legacy-field
    fallback in :func:`_legacy_last_version` reads and never adopts.
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


def _attempt_pinned_upgrade(target: str) -> Tuple[bool, str]:
    """Attempt 2 — explicit version pin. Forces fresh resolution past pip's
    in-process metadata cache, which can otherwise serve a stale "latest"."""
    pinned_cmd = [
        sys.executable, "-m", "pip", "install",
        "--upgrade", "--no-cache-dir", f"atdd=={target}",
    ]
    logger.debug(
        "auto_upgrade attempt %d (pinned): cmd=%s", 2, pinned_cmd,
        extra={"phase": "pip-install", "attempt": 2, "cmd": pinned_cmd, "target": target},
    )
    ok, stderr = _run_with_pep668_retry(pinned_cmd)
    if not ok:
        return False, stderr.strip() or f"pinned install of atdd=={target} failed"
    if not _verify_installed_version(target):
        return False, (
            f"pinned install of atdd=={target} reported success but the installed "
            f"version is still not {target}"
        )
    logger.debug(
        "upgrade verified after pin: atdd %s installed", target,
        extra={"phase": "verify", "attempt": 2, "version": target, "outcome": "match"},
    )
    return True, ""


def _upgrade_via_pip(target: Optional[str]) -> Tuple[bool, str]:
    """Upgrade a pip-installed atdd. Returns (success, failure detail).

    Two-attempt strategy to handle PyPI's CDN propagation window after a
    fresh tag publish:

    1. **Attempt 1** — name-only resolution. ``--no-cache-dir`` busts pip's
       local wheel cache (belt-and-braces). On returncode 0, verify the
       installed version matches what ``_fetch_latest_version`` reported.
    2. **Attempt 2** — explicit version pin: if Attempt 1 succeeded but
       verify failed (pip's resolver served a stale "latest" from its
       in-process metadata cache), retry against ``atdd==<expected>``. The
       version pin forces fresh resolution and is the load-bearing fix.

    Each attempt retries with ``--break-system-packages`` on PEP 668
    refusal (Homebrew/Debian-managed Pythons). Both behaviours are live for
    pip installs and are deliberately confined to this branch — under pipx
    they never applied, because attempt 1 died at module resolution (#1671).
    """
    base_cmd = [sys.executable, "-m", "pip", "install", "--upgrade", "--no-cache-dir", "atdd"]
    logger.debug(
        "auto_upgrade attempt %d: cmd=%s", 1, base_cmd,
        extra={"phase": "pip-install", "attempt": 1, "cmd": base_cmd, "target": target},
    )
    ok, stderr = _run_with_pep668_retry(base_cmd)
    if ok and _verify_installed_version(target):
        logger.debug(
            "upgrade verified: atdd %s installed", target,
            extra={"phase": "verify", "attempt": 1, "version": target, "outcome": "match"},
        )
        return True, ""
    if ok and target:
        logger.debug(
            "pip install returncode=0 but installed != expected=%s; retrying with explicit pin",
            target,
            extra={"phase": "verify", "attempt": 1, "expected": target, "outcome": "mismatch"},
        )
    # Without a known target there is nothing to pin to, whether or not
    # attempt 1 reported success.
    if not target:
        return False, stderr.strip() or "pip reported failure and PyPI was unreachable"
    return _attempt_pinned_upgrade(target)


def _upgrade_via_pipx(target: Optional[str]) -> Tuple[bool, str]:
    """Upgrade a pipx-installed atdd by running pipx. Returns (success, detail).

    A pipx venv ships no pip, so the pip branch cannot reach this install at
    all — it fails at module resolution with "No module named pip" (#1671).
    The only command that upgrades a pipx install is ``pipx`` itself, which
    is exactly what ``upgrade_command()`` already advises.
    """
    pipx = shutil.which("pipx")
    if not pipx:
        return False, (
            "atdd is installed with pipx, but no `pipx` executable is on PATH, "
            "so the upgrade could not be run"
        )

    cmd = [pipx, "upgrade", "atdd"]
    logger.debug(
        "auto_upgrade via pipx: cmd=%s", cmd,
        extra={"phase": "pipx-upgrade", "cmd": cmd, "target": target},
    )
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        return False, detail or f"`pipx upgrade atdd` exited {result.returncode}"

    if not _verify_installed_version(target):
        return False, (
            f"`pipx upgrade atdd` reported success but the installed version is "
            f"still not {target}"
        )
    logger.debug(
        "upgrade verified: atdd %s installed", target,
        extra={"phase": "verify", "mechanism": "pipx", "version": target, "outcome": "match"},
    )
    return True, ""


def auto_upgrade() -> Tuple[bool, str]:
    """Upgrade atdd using the install method actually detected.

    Returns ``(success, detail)``. On failure *detail* carries the underlying
    reason — the stderr of the command that failed, or a statement of why no
    command was run. It is never discarded: a bare "Upgrade failed" is what
    made #1671 take source-reading to diagnose.

    The install method is resolved exactly once, by ``detect_install_method()``,
    and the command executed here is the same command ``upgrade_command()``
    advises. Those two used to be independent code paths — the advice said
    ``pipx upgrade atdd`` and the execution always shelled pip — which made the
    upgrade structurally unreachable on the standard install (#1671).

    Editable installs are reported, never performed: upgrading one means
    pulling the operator's own source checkout, which can conflict or fast-
    forward-fail, and nothing else in this module mutates a working tree on
    the operator's behalf.
    """
    method = detect_install_method()
    advice = upgrade_command()

    try:
        target = _fetch_latest_version()

        if method == "pipx":
            return _upgrade_via_pipx(target)
        if method == "editable":
            return False, (
                "atdd is an editable install; nothing was changed. "
                f"Upgrade it yourself with: {advice}"
            )
        return _upgrade_via_pip(target)
    except Exception as exc:
        # The reason travels to the caller rather than being swallowed here —
        # this is the whole point of the (bool, str) return (#1671).
        logger.debug(
            "auto_upgrade failed: %s", exc,
            extra={"phase": "upgrade", "method": method, "outcome": "exception"},
        )
        return False, f"{type(exc).__name__}: {exc}"


def _resolve_minimum_version() -> Optional[str]:
    """The version floor declared in .atdd/config.yaml, if any."""
    config, _config_path = _load_repo_config()
    if not config:
        return None
    release_cfg = config.get("release", {}) or {}
    return (
        release_cfg.get("minimum_version")
        or config.get("minimum_version")
        or (config.get("toolkit", {}) or {}).get("minimum_version")
    )


def _gate_against_minimum(minimum_version: str) -> None:
    """Gate the installed version against a declared floor. Exits 1 when below."""
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


def _gate_against_pypi() -> None:
    """Gate the installed version against PyPI latest. Exits 1 when outdated."""
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
        minimum_version = _resolve_minimum_version()

    if minimum_version is not None:
        _gate_against_minimum(minimum_version)
        return

    _gate_against_pypi()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--gate", action="store_true", help="Version gate check")
    args = parser.parse_args()

    if args.gate:
        _gate_main()
    else:
        print_update_notice()
