# URN: component:govern-registry:bound-realization-chain:backend:domain
# Runtime: python
# Purpose: The twelve links of the bound-realization proof, one short function each,
#          plus the manifest reading they consume (#1773).
"""The links of the bound-realization chain, and the manifest read they consume.

Split out of :mod:`atdd.coach.validators._bound_realization` so that each link of
the proof is a separate, short, independently readable function. The chain is
twelve sequential checks; expressed as one method it was a single deeply-nested
block where the reader had to hold every prior link in their head to understand
the next, and `coder.refactor.complexity-*` said so.

EVERY LINK HAS THE SAME SHAPE, and it is the shape that makes the chain safe:

    def _link(ctx) -> Optional[BoundRealizationProof]

Returning a proof means "this link BROKE, and here is the named refusal";
returning ``None`` means "this link holds, carry on". A link therefore cannot
accidentally conclude success — only :func:`walk` can, and only after every link
has declined to refuse. That asymmetry is deliberate: the failure mode this
program exists to prevent is a proof that cannot fail, so the code makes refusing
the easy path and proving the one that requires unanimous consent.

The manifest read lives here too, because it is the evidence half of the same
concern: core reads vendored ``atdd.implementation.yaml`` files as DATA and never
imports the module behind ``entrypoint``.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import yaml

from atdd.enforce.resolution import ProviderResolutionError, resolve_provider
from atdd.substrate.binding.composer import realized_conventions
from atdd.substrate.binding.lock_loader import IMPLEMENTATION_MANIFEST
from atdd.substrate.binding.plan import substrate_lock_digest

_log = logging.getLogger(__name__)

__all__ = [
    "Manifest",
    "UnreadableManifestError",
    "iter_implementation_manifests",
    "LINKS",
    "walk",
]

_BOUND = "bound"
_REPORT_FIELD = "report"

#: Where vendored implementation manifests live under a substrate home. Both trees
#: are searched: a workspace package ships the detectors for its own runtime, and
#: an EXTENSION may ship its own detectors targeting that workspace's provider
#: contract. Searching only ``.atdd/workspaces`` is the omission that made every
#: extension-shipped detector invisible in #1359.
SUBSTRATE_TREES: Tuple[str, ...] = ("workspaces", "extensions")


# --------------------------------------------------------------------------- #
# Manifest reading (pure data — no implementation module is ever imported)     #
# --------------------------------------------------------------------------- #
class UnreadableManifestError(Exception):
    """A manifest exists on disk but could not be parsed (acquisition failure)."""

    def __init__(self, path: Path, cause: Exception) -> None:
        super().__init__(f"{path}: {cause}")
        self.path = path


@dataclass(frozen=True)
class Manifest:
    """One vendored ``atdd.implementation.yaml``, read as data."""

    implementation_id: str
    realizes: Tuple[str, ...]
    emits: Tuple[str, ...]
    report: Optional[str]
    path: Path
    #: Whether ``emits_rule_ids`` is absent entirely, as distinct from
    #: declared-and-empty. Both refuse — the rule id is in neither — but they are
    #: different authoring mistakes and the refusal says which. The absent case is
    #: the v1.0 exit-code shape, which ``author_manifest`` still accepts.
    emits_declared: bool = True


def _as_str_list(value: object) -> Tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, (list, tuple)):
        return tuple(str(v) for v in value)
    return ()


def _read_manifest(path: Path) -> Optional[Manifest]:
    """Parse one manifest, or ``None`` when it is not an implementation manifest.

    Raises :class:`UnreadableManifestError` rather than skipping a malformed file:
    a manifest that cannot be read is an acquisition failure to report, not an
    absent one to silently treat as clean (#1716/#1725).
    """
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise UnreadableManifestError(path, exc) from exc
    if not isinstance(data, dict) or data.get("kind") != "implementation":
        return None
    impl_id = data.get("implementation_id")
    if not impl_id:
        return None
    report = data.get(_REPORT_FIELD)
    return Manifest(
        implementation_id=str(impl_id),
        realizes=tuple(realized_conventions(data)),
        emits=_as_str_list(data.get("emits_rule_ids")),
        report=str(report) if report else None,
        path=path,
        emits_declared="emits_rule_ids" in data,
    )


def iter_implementation_manifests(substrate_home: Path) -> List[Manifest]:
    """Every vendored ``atdd.implementation.yaml`` under a substrate home.

    Reads YAML only — the module behind ``entrypoint`` is never imported, so core
    stays free of provider code (#1772 Decision 4).
    """
    out: List[Manifest] = []
    for tree in SUBSTRATE_TREES:
        root = Path(substrate_home) / ".atdd" / tree
        if not root.is_dir():
            continue
        for path in sorted(root.rglob(IMPLEMENTATION_MANIFEST)):
            manifest = _read_manifest(path)
            if manifest is not None:
                out.append(manifest)
    return out


# --------------------------------------------------------------------------- #
# The chain context                                                           #
# --------------------------------------------------------------------------- #
@dataclass
class Chain:
    """What the links share: the rule under proof, the resolver, and what is found.

    Populated as the links succeed, so a later link can name the artifact an
    earlier one selected, and so the finished proof carries the identities that
    make a discharge auditable.
    """

    rule_id: str
    resolver: object  # BoundRealizationResolver — untyped to avoid a cycle
    entry: Dict = field(default_factory=dict)
    manifests: List[Manifest] = field(default_factory=list)
    manifest: Optional[Manifest] = None
    implementation_id: str = ""
    workspace_id: str = ""
    contract: str = "1.0.0"

    def located(self) -> Dict:
        """The artifact identities discovered so far, for the proof record."""
        found: Dict = {}
        if self.implementation_id:
            found["implementation_id"] = self.implementation_id
        if self.workspace_id:
            found["workspace_id"] = self.workspace_id
        if self.manifest is not None:
            found["manifest_path"] = self.manifest.path
        return found

    def concluded(self, basis: str, detail: str):
        """Build a proof on ``basis``, carrying whatever has been located."""
        from atdd.coach.validators._bound_realization import (
            BASIS_OUTCOME,
            BoundRealizationProof,
        )

        return BoundRealizationProof(
            rule_id=self.rule_id,
            outcome=BASIS_OUTCOME[basis],
            basis=basis,
            detail=detail,
            **self.located(),
        )


Link = Callable[[Chain], Optional[object]]


# --------------------------------------------------------------------------- #
# The links, in evaluation order                                              #
# --------------------------------------------------------------------------- #
def substrate_present(ctx: Chain):
    """Is there a consumer-local substrate at all?"""
    r = ctx.resolver
    r._read_lock()
    if r._lock is None and r._lock_error is None:
        return ctx.concluded(
            "no-local-substrate",
            f"no consumer-local binding lock under {r.substrate_home} — this "
            f"branch is owed no provider proof. It grants NO discharge: the rule "
            f"still needs a bind_rule binding or a convention variant.",
        )
    if r._lock_error is not None:
        return ctx.concluded("unreadable-lock", r._lock_error)
    return None


def digest_is_current(ctx: Chain):
    """Does the lock still describe the substrate on disk?"""
    r = ctx.resolver
    recorded = r._lock.get("substrate_lock_digest")
    actual = substrate_lock_digest(r.substrate_home)
    if recorded == actual:
        return None
    return ctx.concluded(
        "stale-substrate-digest",
        f"{r.lock_path} records substrate_lock_digest {recorded!r} but the "
        f"substrate on disk digests to {actual!r} — the lock no longer describes "
        f"this substrate, so it proves nothing about it (and nothing else reads "
        f"this key, so the drift is otherwise silent). Re-run `atdd bind --check`.",
    )


def entry_is_selected(ctx: Chain):
    """EXACT selection on the asserted identity ``convention_id == rule_id``.

    The schema types ``convention_id`` as a free ``minLength: 1`` string, so this
    equality is CHECKED, never inferred — and never matched on an alias, a prefix
    or a case-folded form.
    """
    conventions = ctx.resolver._lock.get("conventions")
    conventions = conventions if isinstance(conventions, list) else []
    entries = [
        c
        for c in conventions
        if isinstance(c, dict) and c.get("convention_id") == ctx.rule_id
    ]
    if not entries:
        return ctx.concluded(
            "no-lock-entry",
            f"no binding-lock entry whose convention_id is exactly "
            f"{ctx.rule_id!r} ({len(conventions)} entr(y/ies) present) — no "
            f"implementation is selected for this rule.",
        )
    if len(entries) > 1:
        return ctx.concluded(
            "ambiguous-lock-selection",
            f"{len(entries)} binding-lock entries claim convention_id "
            f"{ctx.rule_id!r}; exactly one implementation must be selected for a "
            f"convention. Resolve the duplicate before this rule can be proven.",
        )
    ctx.entry = entries[0]
    return None


def entry_is_bound(ctx: Chain):
    """Selected, but is it BOUND? ``legacy-fallback`` says the opposite."""
    disposition = ctx.entry.get("disposition")
    if disposition != _BOUND:
        return ctx.concluded(
            "not-bound",
            f"binding-lock entry for {ctx.rule_id!r} has disposition "
            f"{disposition!r}, not {_BOUND!r} — no provider owns its gating.",
        )
    ctx.implementation_id = str(ctx.entry.get("implementation_id") or "")
    ctx.workspace_id = str(ctx.entry.get("workspace_id") or "")
    ctx.contract = str(ctx.entry.get("contract_version") or "1.0.0")
    return None


def manifest_is_exact(ctx: Chain):
    """Exactly ONE manifest declares the selected ``implementation_id``."""
    r = ctx.resolver
    r._read_manifests()
    if r._manifest_error is not None:
        return ctx.concluded("unreadable-implementation-manifest", r._manifest_error)
    ctx.manifests = r._manifests or []
    candidates = [
        m for m in ctx.manifests if m.implementation_id == ctx.implementation_id
    ]
    if not candidates:
        return ctx.concluded(
            "no-implementation-manifest",
            f"binding-lock selects implementation {ctx.implementation_id!r} for "
            f"{ctx.rule_id!r}, but no {IMPLEMENTATION_MANIFEST} under "
            f"{r.substrate_home}/.atdd/{{{','.join(SUBSTRATE_TREES)}}} declares "
            f"that implementation_id.",
        )
    if len(candidates) > 1:
        paths = ", ".join(str(m.path) for m in candidates)
        return ctx.concluded(
            "ambiguous-implementation-selection",
            f"{len(candidates)} manifests declare implementation_id "
            f"{ctx.implementation_id!r} ({paths}) — the selection is ambiguous, so "
            f"no exact realization can be proven.",
        )
    ctx.manifest = candidates[0]
    return None


def ownership_is_unambiguous(ctx: Chain):
    """Two implementations realizing one convention is an ambiguous binding.

    This is the ``DuplicateConventionError`` the composer raises at compose time,
    re-asserted here at read time.
    """
    owners = [m for m in ctx.manifests if ctx.rule_id in m.realizes]
    if len(owners) <= 1:
        return None
    names = ", ".join(sorted(m.implementation_id for m in owners))
    return ctx.concluded(
        "ambiguous-convention-ownership",
        f"{len(owners)} implementations claim to realize {ctx.rule_id!r} ({names}) "
        f"— an ambiguous binding the operator must resolve; no single realization "
        f"owns this rule.",
    )


def manifest_realizes_the_rule(ctx: Chain):
    """The reverse direction: the manifest must back-reference the rule."""
    if ctx.rule_id in ctx.manifest.realizes:
        return None
    return ctx.concluded(
        "realizes-mismatch",
        f"implementation {ctx.implementation_id!r} is selected for "
        f"{ctx.rule_id!r} but its realizes_convention is "
        f"{list(ctx.manifest.realizes)!r} — it does not claim to own this rule, so "
        f"the lock's selection is unreciprocated.",
    )


def manifest_emits_the_rule(ctx: Chain):
    """Ownership is not emission: a detector may OWN a rule it never EMITS."""
    manifest = ctx.manifest
    if ctx.rule_id in manifest.emits:
        return None
    if manifest.emits_declared:
        shape = f"declares emits_rule_ids={list(manifest.emits)!r}"
    else:
        shape = (
            "declares no emits_rule_ids at all (the v1.0 exit-code shape, which "
            "author_manifest still accepts because it requires emits_rule_ids OR "
            "realizes_convention)"
        )
    return ctx.concluded(
        "emits-mismatch",
        f"implementation {ctx.implementation_id!r} realizes {ctx.rule_id!r} but "
        f"{shape} — nothing states it can emit a violation under this exact rule "
        f"id, so it is not proof that this rule is enforced. Ownership is not "
        f"emission.",
    )


def ownership_is_emitted(ctx: Chain):
    """Re-assert the whole author-time invariant at READ time.

    ``realizes_convention ⊆ emits_rule_ids`` is checked only in
    ``author_manifest._validate_impl_rule_ids``, so a hand-edited manifest
    bypasses it entirely (#1772 Decision 6).
    """
    manifest = ctx.manifest
    unemitted = [c for c in manifest.realizes if c not in manifest.emits]
    if not unemitted:
        return None
    return ctx.concluded(
        "ownership-not-emitted",
        f"manifest {manifest.path} realizes {unemitted!r} without emitting them "
        f"(emits_rule_ids={list(manifest.emits)!r}). realizes_convention must be a "
        f"subset of emits_rule_ids; this is enforced at author time only, so a "
        f"hand-edited manifest reaches here — and a manifest that claims ownership "
        f"it cannot emit is not proof for ANY rule it declares.",
    )


def report_channel_resolves(ctx: Chain):
    """A structured report channel must be DECLARED and PRESENT."""
    manifest = ctx.manifest
    if not manifest.report:
        return ctx.concluded(
            "no-report-channel",
            f"manifest {manifest.path} declares no {_REPORT_FIELD!r} channel — the "
            f"detector has no v1.1 report emitter, so nothing it observes can "
            f"reach a verdict.",
        )
    report_path = manifest.path.parent / manifest.report
    if report_path.is_file():
        return None
    return ctx.concluded(
        "unresolvable-report",
        f"manifest {manifest.path} declares report {manifest.report!r}, but "
        f"{report_path} does not exist — the channel is named, not present.",
    )


def provider_is_runnable(ctx: Chain):
    """The workspace provider CLI must resolve for the locked contract.

    Resolution yields a PATH; core never imports or runs it here.
    """
    home = ctx.resolver.substrate_home
    roots = [home / ".atdd" / tree for tree in SUBSTRATE_TREES] + [home / ".atdd"]
    try:
        resolve_provider(roots, ctx.workspace_id, f"^{ctx.contract}")
    except ProviderResolutionError as exc:
        # Not swallowed: the failure becomes the refusal's own named basis. Logged
        # as well, because an unresolvable provider is an operator problem worth
        # seeing even when only the verdict is rendered.
        _log.info(
            "workspace provider does not resolve — refusing bound-realization proof",
            extra={
                "rule_id": ctx.rule_id,
                "workspace_id": ctx.workspace_id,
                "contract": ctx.contract,
                "error_type": type(exc).__name__,
            },
        )
        return ctx.concluded(
            "provider-unrunnable",
            f"workspace provider {ctx.workspace_id!r} (contract ^{ctx.contract}) "
            f"for {ctx.rule_id!r} does not resolve to a runnable CLI: {exc}",
        )
    return None


def path_b_blocks(ctx: Chain):
    """Bound, exact, reciprocated and runnable is still not enforcement unless
    Path B actually blocks (#1772 Decision 2)."""
    if ctx.resolver._path_b_blocking():
        return None
    return ctx.concluded(
        "path-b-not-blocking",
        f"the realization for {ctx.rule_id!r} is complete, but Path B "
        f"(`atdd enforce`) does not run as a BLOCKING CI gate in "
        f"{ctx.resolver.repo_root}/.github/workflows/atdd-validate.yml — a "
        f"realization nothing blocks on cannot be the proof that an enforced rule "
        f"is enforced.",
    )


#: The chain, in evaluation order. Order is not cosmetic: each link may assume
#: every earlier one held, which is what lets the later links read the artifacts
#: the earlier ones selected.
LINKS: Tuple[Link, ...] = (
    substrate_present,
    digest_is_current,
    entry_is_selected,
    entry_is_bound,
    manifest_is_exact,
    ownership_is_unambiguous,
    manifest_realizes_the_rule,
    manifest_emits_the_rule,
    ownership_is_emitted,
    report_channel_resolves,
    provider_is_runnable,
    path_b_blocks,
)


def walk(rule_id: str, resolver) -> object:
    """Walk every link; the first to refuse decides, else the rule is PROVEN.

    Success is reachable only here, and only when EVERY link declined to refuse.
    No individual link can conclude a discharge.
    """
    from atdd.coach.validators._bound_realization import PROVEN_BASIS

    ctx = Chain(rule_id=rule_id, resolver=resolver)
    for link in LINKS:
        refusal = link(ctx)
        if refusal is not None:
            return refusal
    return ctx.concluded(
        PROVEN_BASIS,
        f"{rule_id!r} is realized by implementation {ctx.implementation_id!r} "
        f"(workspace {ctx.workspace_id!r}, contract {ctx.contract}): selected bound "
        f"in the digest-coherent binding lock, back-referenced in "
        f"realizes_convention, emitted in emits_rule_ids, reporting through "
        f"{ctx.manifest.report!r}, runnable, and blockingly executed by Path B.",
    )
