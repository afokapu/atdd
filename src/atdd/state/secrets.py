"""No secrets in history — invariant I8 (#1400 enforce-merge-authority).

Git history is immutable. Once a raw token is in a commit that reached the protected
branch it is there forever, and the only remaining response is to rotate the credential
and rewrite everyone's history. So the *only* place this can be caught is before the
commit is admitted — which is why this is a required check and not a lint.

Two surfaces carry the risk (spec §5 rule 5, §10 rule 6):

- an **ATDD trailer value** — ``ATDD-Token-Digest`` is exactly the trailer an author
  reaches for when they have an operator token in hand, and pasting the token instead
  of its digest is the natural mistake;
- a **committed projection object** — most plausibly through ``external_refs``, whose
  values come from a provider and are quarantined but not scrubbed.

Only the digest form ``sha256:<hex>`` is ever admissible where a credential could go.

**The report never echoes what it matched.** A validator that prints the secret it found
has published it — into CI logs, into a PR comment, into a bot's transcript. Every
finding here carries a redaction and a short fingerprint instead, which is enough to
locate the value in the working tree and useless to anyone reading the log.

Dependency discipline: stdlib + ``atdd.state`` only.
"""
from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

import yaml

from atdd.state.projection import PROJECTION_SUFFIX
from atdd.state.trailers import DIGEST_RE

_log = logging.getLogger(__name__)

#: The credential shapes that must never reach history. Ordered most-specific first, so a
#: finding is reported under the narrowest kind that explains it.
SECRET_PATTERNS: Tuple[Tuple[str, "re.Pattern[str]"], ...] = (
    ("private_key", re.compile(r"-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----")),
    ("github_pat", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}")),
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}")),
    ("slack_token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}")),
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("bearer_token", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/-]{16,}=*")),
    ("basic_auth_url", re.compile(r"\b[a-z][a-z0-9+.-]*://[^\s/@:]+:[^\s/@]{6,}@")),
    ("private_key_block", re.compile(r"\bBEGIN OPENSSH PRIVATE KEY\b")),
)

#: The one admissible form wherever a credential could otherwise go. Checked *first*:
#: ``sha256:<64 hex>`` can never be a live credential, and admitting it explicitly keeps
#: the digest trailers — the whole point of the trailer group — out of the scanner's way.
ADMISSIBLE_RE = DIGEST_RE


class SecretInHistoryError(ValueError):
    """A raw credential was found on a surface that reaches git history (C003)."""


def redact(value: str, kind: str) -> str:
    """A locator for ``value`` that is useless to anyone who reads it.

    The fingerprint is a truncated digest, so two occurrences of the same secret are
    recognisably the same value without either being recoverable.
    """
    fingerprint = hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]
    return f"<redacted:{kind}:{len(value)}ch:fp={fingerprint}>"


@dataclass(frozen=True)
class SecretFinding:
    """One credential found, named by *where* it is and never by *what* it is."""

    where: str
    kind: str
    redacted: str

    def render(self) -> str:
        return f"{self.where}: {self.kind} — {self.redacted}"


@dataclass(frozen=True)
class SecretReport:
    """The outcome of the no-secrets validator over trailers and/or a projection."""

    scanned: int
    findings: List[SecretFinding] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.findings

    def render(self) -> str:
        if self.ok:
            return f"no secrets in history ({self.scanned} value(s) scanned)"
        lines = [f"secret(s) refused ({len(self.findings)} found, {self.scanned} scanned):"]
        lines.extend(f"  - {finding.render()}" for finding in self.findings)
        lines.append("  history is immutable: rotate the credential and commit only its digest.")
        return "\n".join(lines)


def classify(value: object) -> Optional[str]:
    """The credential kind ``value`` carries, or ``None`` when it is admissible.

    A ``sha256:<hex>`` digest short-circuits: it is the admissible form, and no pattern
    below may reclassify it.
    """
    if not isinstance(value, str) or not value:
        return None
    if ADMISSIBLE_RE.match(value):
        return None
    for kind, pattern in SECRET_PATTERNS:
        if pattern.search(value):
            return kind
    return None


def _walk(node: Any, path: str, findings: List[SecretFinding], counter: List[int]) -> None:
    if isinstance(node, Mapping):
        for key, value in sorted(node.items(), key=lambda kv: str(kv[0])):
            _walk(value, f"{path}.{key}" if path else str(key), findings, counter)
        return
    if isinstance(node, (list, tuple)):
        for index, value in enumerate(node):
            _walk(value, f"{path}[{index}]", findings, counter)
        return
    if isinstance(node, str):
        counter[0] += 1
        kind = classify(node)
        if kind is not None:
            findings.append(SecretFinding(where=path, kind=kind, redacted=redact(node, kind)))


def scan_trailers(mapping: Mapping[str, str]) -> SecretReport:
    """Scan an ``ATDD-*`` trailer mapping for raw credentials (C003)."""
    findings: List[SecretFinding] = []
    counter = [0]
    for key in sorted(mapping):
        counter[0] += 1
        kind = classify(mapping[key])
        if kind is not None:
            findings.append(SecretFinding(
                where=f"trailer {key}", kind=kind, redacted=redact(str(mapping[key]), kind),
            ))
    return SecretReport(scanned=counter[0], findings=findings)


def scan_document(document: Mapping[str, Any], *, uid: Optional[str] = None) -> SecretReport:
    """Scan one projection object — every field, at every depth — for raw credentials."""
    findings: List[SecretFinding] = []
    counter = [0]
    prefix = str(uid or document.get("uid") or "<document>")
    _walk(dict(document), prefix, findings, counter)
    return SecretReport(scanned=counter[0], findings=findings)


def scan_projection(projection_dir: Path) -> SecretReport:
    """Scan every committed projection object under ``projection_dir``."""
    findings: List[SecretFinding] = []
    scanned = 0
    projection_dir = Path(projection_dir)
    if projection_dir.is_dir():
        for path in sorted(projection_dir.glob(f"*{PROJECTION_SUFFIX}"), key=lambda p: p.name):
            document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            report = scan_document(document, uid=path.name)
            scanned += report.scanned
            findings.extend(report.findings)
    return SecretReport(scanned=scanned, findings=findings)


def scan(
    *,
    trailers: Optional[Mapping[str, str]] = None,
    documents: Optional[Mapping[str, Mapping[str, Any]]] = None,
    projection_dir: Optional[Path] = None,
) -> SecretReport:
    """Scan every surface that reaches history in one pass — the CI check (C003)."""
    findings: List[SecretFinding] = []
    scanned = 0
    if trailers:
        report = scan_trailers(trailers)
        scanned += report.scanned
        findings.extend(report.findings)
    for uid, document in sorted((documents or {}).items()):
        report = scan_document(document, uid=uid)
        scanned += report.scanned
        findings.extend(report.findings)
    if projection_dir is not None:
        report = scan_projection(projection_dir)
        scanned += report.scanned
        findings.extend(report.findings)
    if findings:
        _log.warning(
            "secret(s) refused before reaching history",
            extra={"findings": len(findings), "kinds": sorted({f.kind for f in findings})},
        )
    return SecretReport(scanned=scanned, findings=findings)


def secret_kinds() -> Dict[str, str]:
    """The credential kinds this validator recognises, as ``kind -> pattern`` (for docs)."""
    return {kind: pattern.pattern for kind, pattern in SECRET_PATTERNS}
