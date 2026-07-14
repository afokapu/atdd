"""``atdd state`` provider-boundary verbs (#1400 isolate-provider-boundary).

The operator- and CI-facing surface over the seam:

- ``atdd state import-boundary`` — the §8.1 static guard. Exit non-zero if any module reachable
  from a lifecycle module imports a provider, the GitHub API, or shells out to ``gh`` (C001).
- ``atdd state conformance`` — drive the whole workflow against a **bare** git remote with zero
  providers. This is the M5 exit criterion, as a command (C002).
- ``atdd state providers [--provider pkg.mod:factory]`` — what is registered. **Empty by default**,
  name-sorted, and a duplicate name is refused rather than shadowed (E001).
- ``atdd state extensions-lock [--verify]`` — write (or verify) ``.atdd/extensions.lock``: core's
  version and its three policy digests, plus every provider's version and digest (E002).
- ``atdd state mirror`` — run the mirror job. Writes back through ``external_refs.*`` and nothing
  else, **and exits 0 even when a provider fails** (K001, I7).

That last exit code is the load-bearing one, and it is easy to read as a bug. It is not. The
mirror is presentation: if a failing GitHub mirror could return non-zero into a CI job, then
GitHub being down would block a merge, and core would have grown exactly the dependency §8.1
exists to forbid. A failed provider is reported, logged, and **not fatal**. Use ``--strict`` when
you are debugging a provider and want the failure to bite; nothing in CI does.

``--provider pkg.module:factory`` is the composition root. Core imports the string the operator
handed it — never a provider by name. Grep this package for "github": the only hits are the ones
forbidding it.

Dependency discipline: stdlib + ``pyyaml`` + ``atdd.state`` (never a provider).
"""
from __future__ import annotations

import logging
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

from atdd.state import conformance, extensions_lock, import_boundary, provider_seam
from atdd.state.cli_support import add_verb, opt
from atdd.state.extensions_lock import LockError
from atdd.state.projection import PROJECTION_RELATIVE, canonical_bytes, read_projection
from atdd.state.provider_seam import ProviderBoundaryError, ProviderRegistryError, SyncProvider

_log = logging.getLogger(__name__)

#: The ``atdd state`` sub-commands this module owns.
OPS = ("import-boundary", "conformance", "providers", "extensions-lock", "mirror")


#: Register a provider for one invocation. Repeatable, and spelled the same by every verb
#: that takes it — the composition root is the only way a provider ever gets in (spec §8).
def _provider_opt():
    return opt("--provider", action="append", default=None, metavar="PKG.MOD:FACTORY",
               help="Register a provider for this invocation (repeatable).")


def add_parsers(sub) -> None:
    """Register the provider-boundary verbs on the ``atdd state`` sub-parser."""
    add_verb(
        sub, "import-boundary",
        "Prove core's import graph reaches no provider, gh, or GitHub API (spec §8.1).",
        opt("--package", default=None,
            help="The atdd package directory to walk (default: the running one)."),
    )

    add_verb(
        sub, "conformance",
        "Drive the full workflow against a bare git remote with ZERO providers (M5).",
        opt("--work", default=None,
            help="Directory to build the bare remote and clones in (default: a temp dir)."),
    )

    add_verb(
        sub, "providers", "List the registered SyncProviders. Empty by default.",
        _provider_opt(),
    )

    add_verb(
        sub, "extensions-lock",
        "Write .atdd/extensions.lock: core's policy digests + every provider's digest.",
        opt("--verify", action="store_true",
            help="Verify the committed lock instead of writing it (fails on drift)."),
        _provider_opt(),
    )

    add_verb(
        sub, "mirror",
        "Run the mirror job: external_refs.* only, and a provider failure never blocks.",
        _provider_opt(),
        opt("--strict", action="store_true",
            help="Exit non-zero if a provider failed. For debugging — never for CI (I7)."),
        opt("--from", dest="from_dir", default=None, help="Projection directory."),
    )


def _root(args) -> Path:
    return Path(getattr(args, "root", None) or Path.cwd()).resolve()


def _fail(report: str) -> int:
    print(report, file=sys.stderr)
    return 1


def _register(args) -> Dict[str, SyncProvider]:
    """Register every ``--provider`` spec and return the discovered providers (``{}`` for none)."""
    for spec in getattr(args, "provider", None) or []:
        name = provider_seam.register_spec(spec)
        _log.info("registered a sync provider", extra={"provider": name, "spec": spec})
    return provider_seam.discover_providers()


def _cmd_import_boundary(args) -> int:
    package = Path(args.package).resolve() if args.package else None
    try:
        report = import_boundary.check(package)
    except import_boundary.ImportBoundaryError as exc:
        _log.warning(
            "the import-boundary guard could not run",
            extra={"command": "import-boundary", "error": str(exc)},
        )
        return _fail(f"ERROR: {exc}")
    if not report.ok:
        return _fail(report.render())
    print(report.render())
    return 0


def _cmd_conformance(args) -> int:
    if args.work:
        return _conformance_in(Path(args.work).resolve())
    with tempfile.TemporaryDirectory(prefix="atdd-conformance-") as tmp:
        return _conformance_in(Path(tmp))


def _conformance_in(work: Path) -> int:
    work.mkdir(parents=True, exist_ok=True)
    try:
        report = conformance.run_in(work)
    except conformance.ConformanceError as exc:
        _log.warning(
            "the conformance suite could not be set up",
            extra={"command": "conformance", "error": str(exc)},
        )
        return _fail(f"ERROR: {exc}")
    if not report.ok:
        return _fail(report.render())
    print(report.render())
    return 0


def _cmd_providers(args) -> int:
    try:
        providers = _register(args)
    except (ProviderRegistryError, ImportError) as exc:
        _log.warning(
            "a provider could not be registered",
            extra={"command": "providers", "error": str(exc)},
        )
        return _fail(f"ERROR: {exc}")
    if not providers:
        print("no SyncProvider is registered — core runs provider-free (spec §8.1)")
        return 0
    for name in sorted(providers):
        print(name)
    print(f"{len(providers)} provider(s) registered")
    return 0


def _cmd_extensions_lock(args) -> int:
    root = _root(args)
    try:
        providers = _register(args)
        if args.verify:
            report = extensions_lock.verify_repo(root, providers)
            if not report.ok:
                return _fail(report.render())
            print(report.render())
            return 0
        path = extensions_lock.write_lock(root, providers)
    except (LockError, ProviderRegistryError, ImportError) as exc:
        _log.warning("the extensions lock could not be written or verified",
                     extra={"command": "extensions-lock", "verify": bool(args.verify),
                            "error": str(exc)})
        return _fail(f"ERROR: {exc}")
    core = extensions_lock.core_block(root)
    print(f"wrote {path.relative_to(root) if path.is_relative_to(root) else path}")
    for key in extensions_lock.CORE_KEYS:
        print(f"  core.{key:<24} {core[key]}")
    print(f"  {'providers':<29} {sorted(providers) or '(none)'}")
    return 0


def _cmd_mirror(args) -> int:
    """Run the mirror. Exit 0 even when a provider failed — that is the invariant, not a bug (I7)."""
    root = _root(args)
    projection_dir = Path(args.from_dir).resolve() if args.from_dir else root / PROJECTION_RELATIVE
    try:
        providers = _register(args)
    except (ProviderRegistryError, ImportError) as exc:
        _log.warning(
            "a provider could not be registered",
            extra={"command": "mirror", "error": str(exc)},
        )
        return _fail(f"ERROR: {exc}")

    documents = read_projection(projection_dir)
    result = provider_seam.mirror_all(providers, documents)
    try:
        applied = provider_seam.apply_updates(documents, result.updates)
    except ProviderBoundaryError as exc:
        # A refusal at the apply path writes NOTHING, and it is still not a gate: the mirror did
        # not happen, the projection is untouched, and merge authority never knew (I7).
        _log.warning(
            "the mirror's write-back was refused; the projection is untouched",
            extra={"command": "mirror", "rule": exc.rule, "error": str(exc)},
        )
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1 if args.strict else 0

    written = _write_back(projection_dir, documents, applied)
    print(result.render())
    print(f"mirror wrote {len(written)} projection file(s): {written}")
    if result.failed and not args.strict:
        print(
            f"note: {len(result.failed)} provider(s) failed and the mirror still exits 0 — the "
            "mirror is presentation, and its failure may not block a merge (I7)",
        )
    return 1 if (args.strict and not result.ok) else 0


def _write_back(projection_dir: Path, before: Dict[str, dict], after: Dict[str, dict]) -> List[str]:
    """Rewrite only the objects the mirror actually changed, in canonical bytes."""
    written: List[str] = []
    for uid in sorted(after):
        if before.get(uid) == after[uid]:
            continue
        (projection_dir / f"{uid}.yaml").write_bytes(canonical_bytes(after[uid]))
        written.append(uid)
    return written


def dispatch(args) -> int:
    """Run the provider-boundary verb named by ``args.op``."""
    handlers = {
        "import-boundary": _cmd_import_boundary,
        "conformance": _cmd_conformance,
        "providers": _cmd_providers,
        "extensions-lock": _cmd_extensions_lock,
        "mirror": _cmd_mirror,
    }
    return handlers[args.op](args)
