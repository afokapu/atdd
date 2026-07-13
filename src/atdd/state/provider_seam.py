"""The SyncProvider seam — core owns the interface, providers implement it (#1400 §8.2).

The boundary law (spec §8.1) is one sentence: *provider code imports core; core never
imports provider code.* This module is core's half of it — the types a provider speaks in,
the Protocol it satisfies, the registry it registers through, and the **one constrained path**
by which anything it returns may reach the projection.

Five hard properties, and each one is a refusal here rather than a convention elsewhere:

1. ``mirror()`` may return only **bot-namespaced** ``ExternalRefUpdate`` records.
2. ``detect_drift()`` is **alarm-only** — a drift record claiming authoritative lifecycle
   state is a contract violation, not a state change.
3. The extension never edits the projection. It hands core records; core applies them.
4. Core applies provider metadata **only** through :func:`apply_updates`, which writes under
   ``external_refs.*`` and refuses to write anything else — enforced against the ownership
   table (a field whose declared writer is not ``extension-bot`` is not the bot's to touch).
5. Lifecycle code must not read ``external_refs`` — and must not reach this module at all.

Property 5 is why the registry lives *here* and why nothing in the lifecycle closure imports
it: a lifecycle decision that can consult the provider registry is a lifecycle decision that
can depend on GitHub, whatever it happens to do today. :mod:`atdd.state.import_boundary`
proves the import never appears, and it names this module as a string so that proving it does
not itself create the import.

A provider that **raises** is an alarm, never a gate: :func:`mirror_all` degrades a failing
provider to a :class:`DriftAlarm` and returns. That is invariant I7 — the mirror is
presentation, so its failure cannot block a merge (K001).

Dependency discipline: stdlib + ``atdd.state.identity`` / ``atdd.state.ownership`` only. No
provider import, ever — that is the whole point of the file.
"""
from __future__ import annotations

import importlib
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Optional, Protocol, Sequence, Tuple

from atdd.state.identity import UID_RE
from atdd.state.ownership import (
    WRITER_EXTENSION_BOT,
    FieldOwnershipPolicy,
    default_policy,
)

_log = logging.getLogger(__name__)

#: The projection subtree a provider owns — the only one it may ever write (spec §8.2 rule 4).
EXTERNAL_REFS = "external_refs"

#: ``bot:<name>``. The contract's namespace grammar: a mirror writes as a bot or not at all.
NAMESPACE_RE = re.compile(r"^bot:[a-z][a-z0-9-]*$")

#: A provider factory, as the registry and the CLI's ``--provider`` flag both supply one.
ProviderFactory = Callable[[], "SyncProvider"]


class ProviderBoundaryError(ValueError):
    """A provider tried to cross the boundary. Nothing is applied.

    Carries the ``rule`` it broke so the refusal reads as the law it enforces rather than as
    a type error — the operator needs to know *which* of the §8.2 properties was violated.
    """

    def __init__(self, rule: str, detail: str) -> None:
        self.rule = rule
        self.detail = detail
        super().__init__(f"provider boundary violation [{rule}]: {detail} (spec §8.2)")


class ProviderRegistryError(ValueError):
    """A registration could not be made (a duplicate name, or a factory that is not one)."""


# --------------------------------------------------------------------------- #
# The types core owns and providers speak in (D001)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ObjectSnapshot:
    """What core shows a provider: a read-only view of one projection object.

    A *snapshot*, not the document: the provider is handed a copy it cannot write through,
    which is what makes "the extension never edits the projection" true by construction
    rather than by good behaviour.
    """

    uid: str
    slug: Optional[str] = None
    title: Optional[str] = None
    body: Optional[str] = None
    phase: Optional[str] = None
    state: Optional[str] = None
    #: The provider's *own* subtree — its to read, because its to write.
    external_refs: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def of(cls, document: Mapping[str, Any]) -> "ObjectSnapshot":
        return cls(
            uid=str(document["uid"]),
            slug=document.get("slug"),
            title=document.get("title"),
            body=document.get("body"),
            phase=document.get("phase"),
            state=document.get("state"),
            external_refs=dict(document.get(EXTERNAL_REFS) or {}),
        )


@dataclass(frozen=True)
class ExternalRefUpdate:
    """The ONLY record ``mirror()`` may return (``commons:provider-external-ref-update``).

    ``authoritative`` is typed as a field and pinned to ``False`` by validation rather than
    simply omitted: a provider that believes its record *is* authoritative should be able to
    say so and be refused for saying it, not quietly have the claim dropped (I7).
    """

    uid: str
    provider: str
    namespace: str
    ref_kind: str
    ref_value: str
    authoritative: bool = False

    def as_document(self) -> Dict[str, Any]:
        return {
            "uid": self.uid,
            "provider": self.provider,
            "namespace": self.namespace,
            "ref_kind": self.ref_kind,
            "ref_value": self.ref_value,
            "authoritative": self.authoritative,
        }


@dataclass(frozen=True)
class DriftAlarm:
    """An alarm. It reports; it never asserts (spec §8.2 rule 2).

    ``claims`` exists so a drift record that *does* try to assert lifecycle state has somewhere
    to put the assertion — and so the seam can refuse it by name. An alarm carrying no claim is
    the ordinary case: "the mirror and the projection disagree; a human should look".
    """

    uid: str
    provider: str
    kind: str
    detail: str = ""
    authoritative: bool = False
    claims: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ExtensionDigest:
    """What a provider pins itself as, for ``.atdd/extensions.lock`` (spec §10 rule 5)."""

    name: str
    version: str
    digest: str


class SyncProvider(Protocol):
    """The seam (spec §8.2). Core declares it; an extension implements it; core never imports it."""

    name: str

    def mirror(self, objects: Sequence[ObjectSnapshot]) -> List[ExternalRefUpdate]:
        """Project core's truth outward. Returns bot-namespaced external refs — nothing else."""

    def detect_drift(self, objects: Sequence[ObjectSnapshot]) -> List[DriftAlarm]:
        """Report disagreement between the mirror and the projection. Alarm-only."""

    def digest(self) -> ExtensionDigest:
        """Pin this provider's identity and version, so a drifting extension is caught."""


def satisfies_protocol(candidate: Any) -> Tuple[bool, List[str]]:
    """Whether ``candidate`` structurally satisfies :class:`SyncProvider`, and what it lacks.

    Structural, not nominal: a provider that never imports core cannot inherit from a core base
    class, so the seam has to be satisfiable by shape alone (that is what ``Protocol`` is for).
    """
    missing: List[str] = []
    if not isinstance(getattr(candidate, "name", None), str):
        missing.append("name: str")
    for method in ("mirror", "detect_drift", "digest"):
        if not callable(getattr(candidate, method, None)):
            missing.append(f"{method}()")
    return (not missing), missing


# --------------------------------------------------------------------------- #
# Validation at the seam (D001) — the refusals that make the properties true
# --------------------------------------------------------------------------- #
RULE_BOT_NAMESPACE = "bot-namespaced"
RULE_NON_AUTHORITATIVE = "non-authoritative"
RULE_ALARM_ONLY = "alarm-only"
RULE_EXTERNAL_REFS_ONLY = "external-refs-only"
RULE_PROVIDER_IDENTITY = "provider-identity"


def _lifecycle_fields(policy: Optional[FieldOwnershipPolicy]) -> Tuple[str, ...]:
    """Every field the ownership table says the bot does NOT own (spec §7.1).

    Read from the declared policy rather than listed here, so the seam and the field-writer
    gate can never drift into two different ideas of what a provider may touch.
    """
    table = policy or default_policy()
    return tuple(
        sorted(
            name for name, owner in table.fields.items()
            if owner.writer != WRITER_EXTENSION_BOT
        )
    )


def validate_update(
    update: Any, *, provider: Optional[str] = None,
) -> ExternalRefUpdate:
    """Admit one ``ExternalRefUpdate``, or refuse it naming the rule it broke.

    ``provider`` is the provider that actually emitted the record. A record naming a *different*
    provider is refused: otherwise one extension could write into another's subtree, and the
    ownership table — which knows only that "the bot" owns ``external_refs`` — would not catch it.
    """
    ok, missing = _update_shape(update)
    if not ok:
        raise ProviderBoundaryError(
            RULE_EXTERNAL_REFS_ONLY,
            f"mirror() returned {type(update).__name__} missing {missing}; the only admissible "
            "record is an ExternalRefUpdate (commons:provider-external-ref-update)",
        )
    if not UID_RE.match(str(update.uid)):
        raise ProviderBoundaryError(
            RULE_EXTERNAL_REFS_ONLY,
            f"external ref names {update.uid!r}, which is not a work-item uid",
        )
    if not NAMESPACE_RE.match(str(update.namespace)):
        raise ProviderBoundaryError(
            RULE_BOT_NAMESPACE,
            f"namespace {update.namespace!r} is not bot-namespaced; mirror() may return only "
            "records under 'bot:<name>'",
        )
    if update.authoritative:
        raise ProviderBoundaryError(
            RULE_NON_AUTHORITATIVE,
            f"external ref for {update.uid} claims to be authoritative; the mirror is "
            "presentation and never a source of truth (I7)",
        )
    if provider is not None and str(update.provider) != provider:
        raise ProviderBoundaryError(
            RULE_PROVIDER_IDENTITY,
            f"provider {provider!r} returned a record attributed to {update.provider!r}; "
            "a provider writes its own refs and no one else's",
        )
    return ExternalRefUpdate(
        uid=str(update.uid),
        provider=str(update.provider),
        namespace=str(update.namespace),
        ref_kind=str(update.ref_kind),
        ref_value=str(update.ref_value),
        authoritative=False,
    )


def _update_shape(update: Any) -> Tuple[bool, List[str]]:
    missing = [
        name for name in ("uid", "provider", "namespace", "ref_kind", "ref_value")
        if getattr(update, name, None) is None
    ]
    return (not missing), missing


def validate_alarm(
    alarm: Any, *, policy: Optional[FieldOwnershipPolicy] = None,
) -> DriftAlarm:
    """Admit one ``DriftAlarm``, or refuse a record that asserts instead of reporting."""
    missing = [name for name in ("uid", "provider", "kind") if getattr(alarm, name, None) is None]
    if missing:
        raise ProviderBoundaryError(
            RULE_ALARM_ONLY,
            f"detect_drift() returned {type(alarm).__name__} missing {missing}; the only "
            "admissible record is a DriftAlarm",
        )
    if getattr(alarm, "authoritative", False):
        raise ProviderBoundaryError(
            RULE_ALARM_ONLY,
            f"drift record for {alarm.uid} claims authoritative lifecycle state; detect_drift() "
            "is alarm-only and no authoritative state may cross back into core",
        )
    claimed = sorted(set(getattr(alarm, "claims", {}) or {}) & set(_lifecycle_fields(policy)))
    if claimed:
        raise ProviderBoundaryError(
            RULE_ALARM_ONLY,
            f"drift record for {alarm.uid} claims lifecycle field(s) {claimed}; an alarm reports "
            "a disagreement, it does not resolve one",
        )
    return DriftAlarm(
        uid=str(alarm.uid),
        provider=str(alarm.provider),
        kind=str(alarm.kind),
        detail=str(getattr(alarm, "detail", "") or ""),
        authoritative=False,
        claims=dict(getattr(alarm, "claims", {}) or {}),
    )


# --------------------------------------------------------------------------- #
# The constrained apply path (spec §8.2 rule 4) — the ONLY write-back into the projection
# --------------------------------------------------------------------------- #
def apply_updates(
    documents: Mapping[str, Mapping[str, Any]],
    updates: Sequence[ExternalRefUpdate],
    *,
    policy: Optional[FieldOwnershipPolicy] = None,
) -> Dict[str, Dict[str, Any]]:
    """Apply validated updates to a projection, touching ``external_refs.*`` and nothing else.

    Returns a **new** projection: the input is not mutated, so a refusal mid-way cannot leave a
    half-applied document behind. An update naming an object the projection does not carry is
    refused — the mirror does not get to create objects.

    The post-condition is asserted, not assumed: after applying, every field outside the bot's
    ownership must be byte-for-byte what it was. If that ever fails, the refusal names the field.
    """
    table = policy or default_policy()
    lifecycle = _lifecycle_fields(table)
    result: Dict[str, Dict[str, Any]] = {uid: dict(doc) for uid, doc in documents.items()}

    for update in updates:
        admitted = validate_update(update)
        if admitted.uid not in result:
            raise ProviderBoundaryError(
                RULE_EXTERNAL_REFS_ONLY,
                f"external ref names object {admitted.uid}, which is not in the projection; the "
                "mirror reports on core's objects and never creates one",
            )
        document = result[admitted.uid]
        refs = {key: dict(value) if isinstance(value, Mapping) else value
                for key, value in (document.get(EXTERNAL_REFS) or {}).items()}
        subtree = dict(refs.get(admitted.provider) or {})
        subtree[admitted.ref_kind] = admitted.ref_value
        refs[admitted.provider] = subtree
        document[EXTERNAL_REFS] = refs

    for uid, before in documents.items():
        after = result[uid]
        for name in lifecycle:
            if before.get(name) != after.get(name):
                raise ProviderBoundaryError(
                    RULE_EXTERNAL_REFS_ONLY,
                    f"applying the mirror changed {uid}.{name}, which the ownership table says "
                    f"the bot does not own; only external_refs.* is the provider's to write",
                )
    return result


# --------------------------------------------------------------------------- #
# The registry (E001) — empty by default, deterministic, never consulted by lifecycle
# --------------------------------------------------------------------------- #
_REGISTRY: Dict[str, ProviderFactory] = {}


def register_provider(name: str, factory: ProviderFactory) -> None:
    """Register a provider factory under ``name``.

    A duplicate name is **refused**, not shadowed: two providers answering to one name means the
    lock pins one digest and the other one mirrors, which is exactly the drift the lock exists
    to catch. Silently overwriting would make that undetectable.
    """
    if not callable(factory):
        raise ProviderRegistryError(f"provider {name!r} was registered with a non-callable factory")
    if name in _REGISTRY:
        raise ProviderRegistryError(
            f"provider {name!r} is already registered; a name resolves to one provider, and a "
            "second registration is refused rather than silently shadowing the first"
        )
    _REGISTRY[name] = factory


def unregister_provider(name: str) -> None:
    """Drop one registration (no-op if absent)."""
    _REGISTRY.pop(name, None)


def clear_providers() -> None:
    """Drop every registration. Zero providers is core's default and its resting state."""
    _REGISTRY.clear()


def registered_names() -> List[str]:
    """The registered names, sorted. Empty by default — that is the M5 exit criterion."""
    return sorted(_REGISTRY)


def discover_providers() -> Dict[str, SyncProvider]:
    """Instantiate every registered provider, in deterministic name order.

    Deterministic because the mirror's output must not depend on registration order, and empty
    by default because core runs complete with zero providers (C002). A factory that raises is
    an alarm, not an abort: the remaining providers still mirror.
    """
    providers: Dict[str, SyncProvider] = {}
    for name in sorted(_REGISTRY):
        try:
            providers[name] = _REGISTRY[name]()
        except Exception as exc:  # noqa: BLE001 - one broken factory must not abort the rest
            _log.warning(
                "provider factory failed; the provider is skipped and the mirror continues",
                extra={"provider": name, "error": str(exc)},
            )
    return providers


def load_factory(spec: str) -> Tuple[str, ProviderFactory]:
    """Resolve a ``package.module:factory`` spec — the composition root, and the only import.

    Core imports the *string the operator gave it*, never a provider by name. That is what keeps
    the boundary law true while still letting an extension be attached: nothing in this file, or
    anywhere in core, names a provider.
    """
    module_name, _, attribute = spec.partition(":")
    if not module_name or not attribute:
        raise ProviderRegistryError(
            f"provider spec {spec!r} is not 'package.module:factory'"
        )
    module = importlib.import_module(module_name)
    factory = getattr(module, attribute, None)
    if not callable(factory):
        raise ProviderRegistryError(f"provider spec {spec!r} does not name a callable")
    return attribute, factory


def register_spec(spec: str) -> str:
    """Register the provider a ``module:factory`` spec names; return the provider's own name."""
    _, factory = load_factory(spec)
    provider = factory()
    ok, missing = satisfies_protocol(provider)
    if not ok:
        raise ProviderRegistryError(
            f"provider spec {spec!r} produced an object missing {missing}; it does not satisfy "
            "the SyncProvider protocol"
        )
    name = str(provider.name)
    register_provider(name, factory)
    return name


# --------------------------------------------------------------------------- #
# The mirror job (K001) — presentation-only, and a failure is an alarm
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class MirrorResult:
    """What one mirror run produced: the refs it applied, and the alarms it raised."""

    updates: List[ExternalRefUpdate] = field(default_factory=list)
    alarms: List[DriftAlarm] = field(default_factory=list)
    #: Providers that raised, or returned a record the seam refused. Never a gate failure.
    failed: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Whether every provider mirrored cleanly. **Not** a merge verdict (I7).

        A caller must not turn this into an exit code that blocks anything — and none does:
        ``atdd state mirror`` exits 0 with a failed provider, by design (K001).
        """
        return not self.failed

    def render(self) -> str:
        lines = [
            f"mirror applied {len(self.updates)} external ref(s) "
            f"from {len({update.provider for update in self.updates})} provider(s)"
        ]
        lines += [f"  ref  {u.uid} {u.provider}.{u.ref_kind} = {u.ref_value}" for u in self.updates]
        lines += [f"  ALARM {a.provider} {a.uid} {a.kind}: {a.detail}" for a in self.alarms]
        lines += [f"  FAILED {name} (alarm only — merge authority is unaffected)"
                  for name in self.failed]
        return "\n".join(lines)


def mirror_all(
    providers: Mapping[str, SyncProvider],
    documents: Mapping[str, Mapping[str, Any]],
    *,
    policy: Optional[FieldOwnershipPolicy] = None,
) -> MirrorResult:
    """Run every provider's ``mirror()`` and ``detect_drift()``; collect refs and alarms.

    **A provider that raises does not propagate.** It becomes a :class:`DriftAlarm` and the run
    continues — because a mirror is presentation, and presentation failing must not be able to
    stop a merge (spec §12 rule 6, invariant I7). The same is true of a provider whose records
    the seam *refuses*: the refusal is an alarm about that provider, not a failure of core.

    With zero providers this is a no-op returning empty lists, which is the whole M5 claim in
    one line of behaviour.
    """
    snapshots = [ObjectSnapshot.of(documents[uid]) for uid in sorted(documents)]
    updates: List[ExternalRefUpdate] = []
    alarms: List[DriftAlarm] = []
    failed: List[str] = []

    for name in sorted(providers):
        provider = providers[name]
        try:
            emitted = list(provider.mirror(snapshots) or [])
            admitted = [validate_update(update, provider=name) for update in emitted]
        except ProviderBoundaryError as exc:
            _log.warning(
                "a provider's mirror records were refused at the seam; nothing is applied",
                extra={"provider": name, "rule": exc.rule, "error": str(exc)},
            )
            failed.append(name)
            alarms.append(DriftAlarm(uid="", provider=name, kind="boundary-violation",
                                     detail=str(exc)))
            continue
        except Exception as exc:  # noqa: BLE001 - I7: a failing mirror is an alarm, never a gate
            _log.warning(
                "a provider's mirror() raised; it degrades to an alarm and merge authority is "
                "untouched",
                extra={"provider": name, "error": str(exc)},
            )
            failed.append(name)
            alarms.append(DriftAlarm(uid="", provider=name, kind="mirror-failed", detail=str(exc)))
            continue
        updates.extend(admitted)

        try:
            reported = list(provider.detect_drift(snapshots) or [])
            alarms.extend(validate_alarm(alarm, policy=policy) for alarm in reported)
        except ProviderBoundaryError as exc:
            _log.warning(
                "a provider's drift record was refused as an alarm-only violation",
                extra={"provider": name, "rule": exc.rule, "error": str(exc)},
            )
            failed.append(name)
            alarms.append(DriftAlarm(uid="", provider=name, kind="boundary-violation",
                                     detail=str(exc)))
        except Exception as exc:  # noqa: BLE001 - same law: an alarm channel cannot become a gate
            _log.warning(
                "a provider's detect_drift() raised; it degrades to an alarm",
                extra={"provider": name, "error": str(exc)},
            )
            failed.append(name)
            alarms.append(DriftAlarm(uid="", provider=name, kind="drift-failed", detail=str(exc)))

    return MirrorResult(updates=updates, alarms=alarms, failed=sorted(set(failed)))
