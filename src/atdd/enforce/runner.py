# URN: component:enforce-binding-plan:run-binding-plan:runner:backend:domain
# Runtime: python
# Purpose: Lock-driven runner — read binding.lock.yaml, resolve+subprocess each
#          bound rule's provider, bridge raw v1.1 JSON -> disposition verdict ->
#          aggregate exit code. Pure consumer; never imports a provider (V5).
"""The lock-driven enforcement runner (#1238 phase ``runner-and-bridge``).

Pipeline per ``disposition: bound`` convention in ``binding.lock.yaml``:

  1. resolve ``(workspace_id, implementation_id, contract_version)`` -> a vendored
     provider CLI (:mod:`atdd.enforce.resolution`, keyed off ``workspace_id``);
  2. compute the rule's scan roots/excludes (:mod:`atdd.enforce.conventions`);
  3. SUBPROCESS the provider CLI over the roots — core never imports it (V5) —
     and parse the RAW v1.1 violation JSON off stdout;
  4. ADAPT each raw record to ``file:line:col`` + join the rule's severity from
     the convention node;
  5. evaluate the rule's disposition NON-RAISING (FAIL is a value, D-2);
  6. aggregate every per-rule verdict into one process exit code.

Substrate resolution: a consumer with its own ``.atdd/binding.lock.yaml`` uses
it; otherwise the runner falls back to the toolkit's own installed substrate
(the repo shipping this ``atdd`` package) and scans the consumer's tree. This is
the single accessor isolating the lock/config read so #1168's State Store can
later swap it (D-3).

KNOWN LIMITATION (honest, #1238 §5 / V1): the vendored python-pytest provider
ships a working v1.1 report channel for exactly ONE bound rule today
(``coder.logging.print``); the other 25 declare no report channel. Such rules
are reported ``unrunnable`` (loudly — never silently skipped) and the
``--conformance`` verdict fails until the workspace package generalizes its CLI
(D-1 / phase ``generalize-cli``). The runner verb, the subprocess bridge, the
disposition verdict, and the exit-code aggregation are complete and proven by
the one runnable rule.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import yaml

from atdd.enforce.conventions import (
    RuleMetadata,
    compute_scan_policy,
    is_interlocking_rule,
    load_bound,
    resolve_interlocking_layout,
    rule_metadata,
    select_rules,
)
from atdd.enforce.dispositions import fails_on_violation
from atdd.enforce.provider_env import provider_env
from atdd.enforce.resolution import (
    ProviderResolutionError,
    ResolvedProvider,
    resolve_provider,
)

# Per-impl manifest field naming the runnable v1.1 report-emitting test (the
# detector's structured report channel). Mirrors the vendored ``cli/scan.py``
# ``REPORT_FIELD`` (#1238 V1 / generalize-cli): the runner resolves the report
# test from each implementation's manifest rather than keying off one hardcoded
# filename, so every bound detector is runnable — not just ``coder.logging.print``.
_PROVIDER_REPORT_FIELD = "report"


class EnforceUsageError(Exception):
    """A usage / wiring error -> process exit code 2 (could not run as configured)."""


@dataclass(frozen=True)
class RuleVerdict:
    rule_id: str
    workspace_id: str
    status: str  # "pass" | "fail" | "skip" | "exempt" | "unrunnable"
    raw_violation_count: int = 0
    locations: List[str] = field(default_factory=list)
    detail: str = ""

    @property
    def failed(self) -> bool:
        return self.status == "fail"


@dataclass(frozen=True)
class EnforceResult:
    verdicts: List[RuleVerdict]
    report: str

    @property
    def passed(self) -> bool:
        return not any(v.failed for v in self.verdicts)

    @property
    def exit_code(self) -> int:
        return 0 if self.passed else 1


# --------------------------------------------------------------------------- #
# Substrate / config access (the single accessor — D-3)
# --------------------------------------------------------------------------- #
def _toolkit_root() -> Path:
    """Repo root of the ATDD package shipping this runner (fallback substrate)."""
    # src/atdd/enforce/runner.py -> parents: [0]=enforce [1]=atdd [2]=src [3]=repo
    return Path(__file__).resolve().parents[3]


def resolve_substrate_home(repo_root: Path) -> Path:
    """Where ``.atdd/binding.lock.yaml`` + vendored providers live for this run.

    A consumer-local substrate wins; otherwise fall back to the toolkit install
    so an un-bound consumer still gets the toolkit's bound rules enforced over
    its code.
    """
    if (repo_root / ".atdd" / "binding.lock.yaml").is_file():
        return repo_root
    return _toolkit_root()


def load_config(repo_root: Path) -> dict:
    """Parse ``<repo_root>/.atdd/config.yaml``; ``{}`` when absent.

    A malformed config is a usage/wiring error (exit 2), NOT a verdict — it means
    the command could not run as configured.
    """
    cfg_path = repo_root / ".atdd" / "config.yaml"
    if not cfg_path.is_file():
        return {}
    try:
        data = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise EnforceUsageError(f"malformed .atdd/config.yaml: {exc}") from exc
    return data if isinstance(data, dict) else {}


def _bound_conventions(substrate_home: Path, rules: Optional[set] = None) -> list[dict]:
    """The ``bound`` convention entries, optionally narrowed to ``rules``.

    Thin seam over the resolution helpers in :mod:`atdd.enforce.conventions`; kept
    here because it is the name callers and tests already bind to.
    """
    bound = load_bound(substrate_home, EnforceUsageError)
    return select_rules(bound, rules, EnforceUsageError)


def _candidate_roots(substrate_home: Path) -> list[Path]:
    atdd_dir = substrate_home / ".atdd"
    return [atdd_dir / "workspaces", atdd_dir / "extensions", atdd_dir]


# --------------------------------------------------------------------------- #
# Provider invocation (the subprocess boundary — V5)
# --------------------------------------------------------------------------- #
def _resolve_impls_root(substrate_home: Path, implementation_id: str) -> Optional[Path]:
    """The impls-root owning ``implementation_id``, iff it ships a v1.1 report channel.

    Reads the impl manifest's ``report:`` field and checks the named test file is
    present next to the manifest — the exact runnable-detection the vendored
    ``cli/scan.py`` performs (``_report_test_name`` + ``test_path.is_file()``).
    Replacing the prior hardcoded ``test_logging_print_report.py`` lets all bound
    detectors run, not just ``coder.logging.print`` (#1238 V1).

    Searches BOTH vendored trees. A workspace package ships the detectors for its
    own runtime; an EXTENSION may ship its own detectors targeting that workspace's
    provider contract (the train-interlocking extension does). Searching only
    ``.atdd/workspaces`` made every extension-shipped detector ``unrunnable`` while
    enforce still reported PASS — a false green (#1359).

    Returns the root the owning manifest sits under (``…/implementations``), which
    the caller forwards to the provider CLI as ``--impls-root``; ``None`` when the
    impl is absent or ships no report channel.
    """
    roots = (substrate_home / ".atdd" / "workspaces", substrate_home / ".atdd" / "extensions")
    for root in roots:
        if not root.is_dir():
            continue
        for manifest in sorted(root.rglob("atdd.implementation.yaml")):
            try:
                data = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
            except (OSError, yaml.YAMLError):
                continue
            if data.get("implementation_id") != implementation_id:
                continue
            report = data.get(_PROVIDER_REPORT_FIELD)
            if not report:
                return None
            if not (manifest.parent / str(report)).is_file():
                return None
            # cli/scan.py discovers impls as children of the root it is given.
            return manifest.parent.parent
    return None


def _invoke_provider(
    provider: ResolvedProvider,
    implementation_id: str,
    scan_roots: list[str],
    scan_excludes: list[str],
    graph_roots: Optional[list[str]] = None,
    impls_root: Optional[Path] = None,
    interlocking_layout: Optional[dict] = None,
) -> list[dict]:
    """Subprocess the provider CLI over ``scan_roots``; parse RAW v1.1 JSON.

    Core NEVER imports the provider — the only contract is "run a CLI, read the
    v1.1 JSON array off stdout". A non-zero provider exit is a run/usage failure
    of the provider itself (stdout empty), raised rather than mis-read as clean.

    What the subprocess is told — the scan surface, ``graph_roots``, the
    ``interlocking_layout`` and the cache suppression — is
    :func:`atdd.enforce.provider_env.provider_env`; this function only runs it and
    reads the result.
    """
    env = provider_env(
        implementation_id,
        scan_roots,
        scan_excludes,
        graph_roots=graph_roots,
        interlocking_layout=interlocking_layout,
    )
    argv = [sys.executable, str(provider.provider_cli_path)]
    if impls_root is not None:
        # Without this the provider CLI defaults to its OWN implementations/ dir and
        # cannot discover a detector shipped by an extension package.
        argv += ["--impls-root", str(impls_root)]
    proc = subprocess.run(
        argv,
        env=env,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise EnforceUsageError(
            f"provider CLI failed (exit {proc.returncode}) for {implementation_id!r}: "
            f"{proc.stderr.strip() or '(no stderr)'}"
        )
    out = proc.stdout.strip()
    if not out:
        return []
    try:
        records = json.loads(out)
    except json.JSONDecodeError as exc:
        raise EnforceUsageError(
            f"provider CLI emitted non-JSON stdout for {implementation_id!r}: {exc}"
        ) from exc
    return list(records) if isinstance(records, list) else []


def _adapt_location(raw: dict) -> str:
    """Adapt one RAW v1.1 record to a ``file:line:col`` location string."""
    file = raw.get("file")
    line = raw.get("line")
    col = raw.get("col")
    if file is not None and line is not None and col is not None:
        return f"{file}:{line}:{col}"
    # v1.0.0 fallback record carries only ``location``.
    return str(raw.get("location", file or "."))


def _records_for_rule(raw: list[dict], rule_id: str) -> list[dict]:
    """Keep only RAW records whose ``rule_id`` matches the bound convention.

    A multi-rule detector emits SEVERAL rule_ids from one run (e.g. the
    complexity detector emits cyclomatic/nesting/length/params/cognitive; the
    security detector emits sql-injection/missing-auth/hardcoded-secret). Each
    bound convention must be judged on its OWN violations, not the detector's
    whole output — otherwise a sibling rule is credited (or blamed) for another
    rule's findings. v1.1 records always carry ``rule_id``; the v1.0.0 fallback
    record sets ``rule_id == implementation_id`` (which equals the bound
    convention for the single-rule print detector), so it matches too.
    """
    return [r for r in raw if r.get("rule_id") == rule_id]


def _verdict_for_rule(meta: RuleMetadata, raw: list[dict]) -> str:
    """Non-raising disposition verdict (D-2), TOTAL over the treatment vocabulary
    (#1424 E001).

    strict / suppress-and-clean fail on any violation; advisory /
    documentation-only never fail. The mapping is delegated to the disposition
    model's :func:`fails_on_violation` so the treatment namespace is named in
    exactly one place. Previously ONLY ``advisory`` was special-cased, so
    ``documentation-only`` fell through to fail-on-any and failed builds it must
    not have (e.g. the bound documentation-only rule ``tester.filename.urn``)."""
    if not raw:
        return "pass"
    return "fail" if fails_on_violation(meta.disposition) else "pass"


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def enforce(
    repo_root: Path,
    *,
    path_override: Optional[list[str]] = None,
    rules: Optional[set] = None,
) -> EnforceResult:
    """Enforce every ``bound`` convention against ``repo_root``.

    ``rules`` narrows the run to the named conventions — one provider subprocess per
    selected rule instead of one per bound rule. Omitted, every bound convention runs,
    so existing callers (`atdd enforce`, the post-commit hook, CI) are unaffected. A
    selection naming an unbound or unknown rule raises rather than running nothing.

    Raises :class:`EnforceUsageError` (exit 2) on a wiring failure (malformed
    config/lock, unresolvable provider, provider crash).
    """
    repo_root = repo_root.resolve()
    substrate_home = resolve_substrate_home(repo_root)
    config = load_config(repo_root)  # may raise EnforceUsageError (exit 2)
    bound = _bound_conventions(substrate_home, rules)

    if not bound:
        return EnforceResult(verdicts=[], report="enforce: no bound conventions — clean no-op.")

    candidate_roots = _candidate_roots(substrate_home)
    provider_cache: dict[str, ResolvedProvider] = {}
    verdicts: List[RuleVerdict] = []

    for conv in bound:
        rule_id = str(conv.get("convention_id"))
        impl_id = str(conv.get("implementation_id") or rule_id)
        workspace_id = str(conv.get("workspace_id") or "")
        contract = str(conv.get("contract_version") or "1.0.0")
        meta = rule_metadata(substrate_home, rule_id)

        policy = compute_scan_policy(repo_root, config, rule_id, path_override=path_override)
        if policy.exempt:
            verdicts.append(
                RuleVerdict(rule_id, workspace_id, "exempt", detail=policy.exempt_reason)
            )
            continue
        if not policy.scan_roots:
            verdicts.append(
                RuleVerdict(rule_id, workspace_id, "skip", detail="no scan roots for this rule")
            )
            continue

        # Honest gate: a rule whose vendored impl ships no v1.1 report channel
        # cannot enforce over consumer code yet (workspace generalization, D-1).
        impls_root = _resolve_impls_root(substrate_home, impl_id)
        if impls_root is None:
            verdicts.append(
                RuleVerdict(
                    rule_id,
                    workspace_id,
                    "unrunnable",
                    detail="no v1.1 report channel in vendored provider (awaits generalize-cli)",
                )
            )
            continue

        cache_key = f"{workspace_id}@{contract}"
        if cache_key not in provider_cache:
            try:
                provider_cache[cache_key] = resolve_provider(
                    candidate_roots, workspace_id, f"^{contract}"
                )
            except ProviderResolutionError as exc:
                raise EnforceUsageError(
                    f"cannot resolve provider {workspace_id!r} ({contract}) for "
                    f"{rule_id!r}: {exc}"
                ) from exc
        provider = provider_cache[cache_key]

        # Scope the per-repo interlocking layout to the interlocking rules only —
        # resolve the declared block once and forward it via env ONLY for a
        # coder.train.interlocking-* subprocess, never leaking it onto unrelated
        # rule subprocesses (#1595).
        layout = (
            resolve_interlocking_layout(config)
            if is_interlocking_rule(rule_id)
            else None
        )

        raw = _invoke_provider(
            provider,
            impl_id,
            policy.scan_roots,
            policy.scan_excludes,
            policy.graph_roots,
            impls_root=impls_root,
            interlocking_layout=layout,
        )
        # A multi-rule detector emits several rule_ids in one run; judge this
        # bound convention only on its own rule_id's records.
        raw = _records_for_rule(raw, rule_id)
        status = _verdict_for_rule(meta, raw)
        locations = [_adapt_location(r) for r in raw]
        verdicts.append(
            RuleVerdict(
                rule_id,
                workspace_id,
                status,
                raw_violation_count=len(raw),
                locations=locations,
                detail="" if status == "pass" else f"{len(raw)} violation(s)",
            )
        )

    return EnforceResult(verdicts=verdicts, report=_render(verdicts))


def conformance(repo_root: Path) -> tuple[bool, str]:
    """V1 conformance: is every ``bound`` rule runnable end-to-end?

    Honestly reports per-rule runnability (a rule is runnable iff its vendored
    impl ships a v1.1 report channel). Returns ``(ok, report)`` where ``ok`` is
    True iff EVERY bound rule is runnable — today that is false (1/26), so the
    verb exits non-zero, surfacing the true 25-of-26 gap rather than a false
    green. It NEVER emits the provider's ``report test missing`` string (it does
    not drive the legacy REPORT_TEST resolution path).
    """
    repo_root = repo_root.resolve()
    substrate_home = resolve_substrate_home(repo_root)
    bound = _bound_conventions(substrate_home)
    if not bound:
        return True, "conformance: no bound conventions."

    runnable: list[str] = []
    unrunnable: list[str] = []
    for conv in bound:
        rule_id = str(conv.get("convention_id"))
        impl_id = str(conv.get("implementation_id") or rule_id)
        if _resolve_impls_root(substrate_home, impl_id) is not None:
            runnable.append(rule_id)
        else:
            unrunnable.append(rule_id)

    ok = not unrunnable
    lines = [
        f"conformance: {len(runnable)}/{len(bound)} bound rules runnable end-to-end.",
    ]
    for r in runnable:
        lines.append(f"  [runnable]   {r}")
    for r in unrunnable:
        lines.append(f"  [unrunnable] {r} — no v1.1 report channel (awaits generalize-cli)")
    if not ok:
        lines.append("")
        lines.append(
            f"V1 NOT MET: {len(unrunnable)} bound rule(s) cannot run over consumer code. "
            "The provider CLI must ship a per-impl v1.1 report channel (#1238 phase "
            "generalize-cli / D-1) before conformance is green."
        )
    return ok, "\n".join(lines)


def _render(verdicts: List[RuleVerdict]) -> str:
    lines: List[str] = []
    for v in verdicts:
        # A preserved exemption is SILENT: the legacy in-core validator produces
        # no finding for an exempt rule, so the runner must not name it either
        # (V4 — the exemption is preserved, not merely noted). Counted below.
        if v.status == "exempt":
            continue
        tag = v.status.upper()
        lines.append(f"[{tag}] {v.rule_id} [{v.workspace_id}] {v.detail}".rstrip())
        for loc in v.locations:
            lines.append(f"    {v.rule_id} @ {loc}")
    failed = [v for v in verdicts if v.failed]
    enforced = [v for v in verdicts if v.status in ("pass", "fail")]
    exempt = [v for v in verdicts if v.status == "exempt"]
    not_run = [v for v in verdicts if v.status in ("skip", "exempt", "unrunnable")]
    if exempt:
        lines.append(
            f"[EXEMPT] {len(exempt)} rule(s) exempt for this scan scope "
            f"(toolkit CLI tree exemption preserved)."
        )
    lines.append("")
    lines.append(
        f"enforce verdict: {'FAIL' if failed else 'PASS'} — "
        f"{len(enforced)} rule(s) enforced, {len(failed)} failed, {len(not_run)} not run "
        f"(skip/exempt/unrunnable)."
    )
    return "\n".join(lines)
