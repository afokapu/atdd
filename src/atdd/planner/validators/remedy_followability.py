# Phase: GREEN
# Layer: backend.domain
"""Remedy-followability scanner for convention-node prose (#1965).

A ``fix_hint`` is an executable promise: if it names a file, that file must
exist; if it names a verb, that verb must resolve. Nothing read a ``fix_hint``,
so when #1303 removed the ``atdd issue`` verb and the smoke-acceptance validator
was renamed, every hint quoting them stayed exactly as written — and the reader
who followed one was sent nowhere, while blocked.

**Why this scanner is mostly exclusions.** A naive scan of the 316 convention
nodes finds 179 of 332 concrete repo paths absent from disk. That is 30x the
real defect count, and a rule shipped against it would have needed 173
exceptions — which is how a gate becomes noise nobody reads. Decomposed by
cause, 137 are ``source.legacy_path`` provenance (a historical record carrying a
``legacy_sha``, naming a monolith that was deliberately deleted — pointing at a
deleted file is what provenance IS), 34 are illustrative example paths (a naming
rule's negative example must NOT exist), and 22 are operative prose. Six of
those are real. Six is affordable, which is the whole reason this rule can be
``strict`` at zero rather than another advisory reporter.

**Root.** The checkout, and ``platform``-gated at the validator. In a consumer
repo that installed ATDD, nodes arrive only from the installed package and the
paths they quote are paths in the *toolkit* repo, which will never exist in a
consumer tree — so an ungated rule would flag nearly every path as absent in
somebody else's repo, for defects they neither caused nor can fix. That is the
leak ``is_atdd_source_repo()`` exists to prevent (#272/#276). The installed
package also carries 0 of ``plan/``, ``docs/`` and ``.atdd/``, so it is not a
root this rule could resolve against at all.

Rule: planner.convention.remedy-must-be-followable
"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional, Sequence, Tuple

import yaml

# ---------------------------------------------------------------------------
# Exclusion causes. Each is a way the naive count of 179 was wrong.
# ---------------------------------------------------------------------------
EXCLUSION_PROVENANCE = "provenance"
EXCLUSION_ILLUSTRATIVE = "illustrative"
EXCLUSION_FORMULA = "schematic-formula"
EXCLUSION_EXCLUDED_MECHANISM = "excluded-mechanism"
EXCLUSION_CONDITIONAL = "conditional"
EXCLUSION_GITIGNORED = "gitignored-runtime"
EXCLUSION_HISTORICAL = "historical-record"
EXCLUSION_VERB_DOCUMENTED = "verb-documented-as-retired"

KIND_ABSENT_PATH = "absent_path"
KIND_RETIRED_VERB = "retired_verb"


@dataclass(frozen=True)
class RetiredVerb:
    """A CLI verb that no longer resolves, and the live verb that replaced it.

    The replacement is not decoration. A remedy that says only "that verb is
    gone" is itself unfollowable — the reader is blocked either way.
    """

    replacement: str
    reason: str


#: Verbs removed from the CLI whose spelling still appears in convention prose.
RETIRED_VERBS: Dict[str, RetiredVerb] = {
    "atdd issue ": RetiredVerb(
        replacement=(
            "`atdd coach transition <N> <PHASE>` (for `atdd issue <N> --status "
            "<PHASE>`) or `atdd coach issues open` (for `atdd issue open`)"
        ),
        reason=(
            "#1303 removed the `atdd issue` verb; both replacements name "
            "themselves as such in their own --help"
        ),
    ),
}


@dataclass(frozen=True)
class Finding:
    """One unfollowable remedy: a node, the prose it lives in, and the remedy."""

    node_id: str
    node_path: Path
    keypath: str
    token: str
    kind: str
    detail: str


# ---------------------------------------------------------------------------
# Tokenizer
# ---------------------------------------------------------------------------
# The charset ADMITS the placeholder characters `<>{}*` so that a template can
# be recognised and rejected. The lab's tokenizer stopped at `<`, which cut
# `…/nodes/planner.<artifact>.definition.convention.yaml` down to
# `…/nodes/planner` — a truncation that defeated its own placeholder guard,
# because the character it would have rejected had already been discarded.
_TOKEN = re.compile(
    r"(?<![\w./-])"
    r"((?:src|plan|docs|contracts|telemetry|\.atdd|tests|scripts)"
    r"/[A-Za-z0-9_./<>{}*-]+)"
)
_PLACEHOLDER = re.compile(r"[<>{}*]")
_EXTENSION = re.compile(r"\.[A-Za-z0-9]{1,12}$")
_TRAILING_PUNCT = ".,;:'\")"


def path_tokens(text: str) -> List[str]:
    """Every repo-path reference in *text*, in order, deduped.

    A candidate must end in a file extension or a ``/``. That single condition
    retires two of the naive scan's false positives at their cause: ``tests/ADRs``
    ("...or routed to tests/ADRs") and ``plan/test/code`` ("the plan/test/code
    themes align to the planner/tester/coder archetypes") both use the slash to
    mean "or", and neither is shaped like a path. Requiring the shape is more
    honest than naming the two tokens, because the next prose disjunction
    someone writes is excluded for the same reason rather than needing its own
    exception.
    """
    out: List[str] = []
    for match in _TOKEN.finditer(text):
        token = match.group(1).rstrip(_TRAILING_PUNCT)
        if not token or _PLACEHOLDER.search(token):
            continue
        if not (token.endswith("/") or _EXTENSION.search(token)):
            continue
        if token not in out:
            out.append(token)
    return out


# ---------------------------------------------------------------------------
# Exclusion rules
# ---------------------------------------------------------------------------
_ILLUSTRATIVE_KEYS = frozenset({"examples", "values", "positive", "negative"})

#: Keys whose strings a reader is expected to ACT on. Mirrors the cause split
#: the issue's measurement was taken with, so the census stays comparable.
OPERATIVE_KEYS = frozenset(
    {
        "operational_guidance",
        "normative_text",
        "fix_hint",
        "statement",
        "text",
        "notes",
        "description",
    }
)

_FORMULA = re.compile(r"\bFormula:")
_EXCLUSION_HEADER = re.compile(r"excluded mechanisms|what is NOT", re.IGNORECASE)
_CONDITIONAL_GUARD = re.compile(r"\b(when|if) present\b", re.IGNORECASE)
_RETIREMENT = re.compile(
    r"\b(retired|superseded|deleted|removed|no longer)\b", re.IGNORECASE
)

#: How far back to look for a retirement marker. Scoped deliberately: the
#: `.atdd/labels.yaml` fix_hint later says "remove the auto-closing keyword",
#: and a whole-string search for "removed" would excuse defect #3 on the
#: strength of a word that has nothing to do with it. The window looks only
#: BEHIND the token, where a marker actually governs it.
_RETIREMENT_WINDOW = 80


def _negated(text: str, token: str) -> bool:
    """``no <token>`` — a statement of absence rather than a pointer."""
    return re.search(r"\bno\s+" + re.escape(token), text, re.IGNORECASE) is not None


def _conditional(text: str, token: str) -> bool:
    """``if <token> exists`` / ``when present`` — a predicate, not a pointer."""
    if re.search(
        r"\bif\s+" + re.escape(token) + r"\s+exists", text, re.IGNORECASE
    ):
        return True
    return _CONDITIONAL_GUARD.search(text) is not None


def _declared_retired(text: str, token: str) -> bool:
    """A retirement marker governs *token* from behind, on its own line.

    The tense is the signal, and it is the sharpest line in this rule: the same
    file-shaped token is deliberate in one node and a defect in another.
    ``coach.execution.atomic-registry-write`` says #1270 "retired the
    `.atdd/manifest.yaml` mirror" — past tense, a record of what used to be.
    ``coach.lifecycle.no-terminal-before-lifecycle-satisfied`` says the phase
    labels "live under `.atdd/labels.yaml`" — present tense, a pointer, and the
    file is not there. Keyed on the token instead of the tense, this exclusion
    would excuse the very defect the rule exists to catch.
    """
    index = text.find(token)
    if index < 0:
        return False
    line_start = text.rfind("\n", 0, index) + 1
    window_start = max(line_start, index - _RETIREMENT_WINDOW)
    return _RETIREMENT.search(text[window_start:index]) is not None


#: Markers that turn a verb mention from an instruction into a record. Wider
#: than the path-side set because English puts the retirement AFTER the verb
#: ("`atdd issue open` became ..."), and deliberately kept separate so widening
#: it cannot weaken the path rule.
_VERB_RETIREMENT = re.compile(
    r"\b(retired|removed|superseded|deleted|no longer|became|replaced|"
    r"replacement)\b",
    re.IGNORECASE,
)
#: Sentence boundary: a terminator followed by whitespace. A version or a
#: filename ("4.83.0", "x.py") has no whitespace after its dots, so neither
#: splits. Scoping to the SENTENCE rather than a character window is what stops
#: a marker in one sentence from excusing an instruction in the next.
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def _sentence_around(text: str, index: int) -> str:
    """The sentence of *text* containing the character at *index*."""
    starts = [0] + [m.end() for m in _SENTENCE_SPLIT.finditer(text)]
    low = max(start for start in starts if start <= index)
    after = [start for start in starts if start > index]
    return text[low : min(after) if after else len(text)]


def verb_documented_as_retired(text: str, verb: str) -> bool:
    """Every mention of *verb* in *text* is governed by a retirement marker.

    A rule about retired verbs has to be able to NAME one in order to say what
    replaced it — this node's own fix_hint says "`atdd issue <N> --status
    <PHASE>` became `atdd coach transition <N> <PHASE>`" and would otherwise
    convict itself. This is the verb-side of the tense test the path rule
    already applies.

    ``all``, not ``any``: one instructional mention is a defect no matter how
    much retirement prose surrounds it. A node that explains the replacement
    and then still tells the reader to run the dead verb has not been repaired.

    The marker must govern the verb from within the SAME SENTENCE. A character
    window was tried first and was wrong — in "`atdd issue open` was removed in
    #1303. To list issues, run atdd issue open", a 60-character window let
    "removed" reach across the full stop and excuse the live instruction after
    it, which is precisely the loophole the ``all`` is there to close.
    """
    mentions = list(re.finditer(re.escape(verb), text))
    if not mentions:
        return False
    for match in mentions:
        if not _VERB_RETIREMENT.search(_sentence_around(text, match.start())):
            return False
    return True


def _git_ignored(repo_root: Path, token: str) -> bool:
    """``git check-ignore`` — the oracle for gitignored runtime state.

    ``.atdd/runtime/``, ``.atdd/state/state.sqlite`` and
    ``.atdd/smoke-evidence/`` exist in a full checkout and are absent from a
    worktree purely because they are gitignored. Asking git rather than naming
    them means the exclusion cannot outlive the paths: the day one is taken out
    of ``.gitignore`` is the day it stops being excused, which is exactly the day
    it becomes a real defect. A hardcoded list would keep excusing it forever.
    """
    try:
        completed = subprocess.run(
            ["git", "check-ignore", "-q", token],
            cwd=str(repo_root),
            capture_output=True,
            check=False,
        )
    except OSError:
        return False
    return completed.returncode == 0


def classify(
    keypath: Sequence[str],
    text: str,
    token: str,
    repo_root: Path,
) -> Optional[str]:
    """The exclusion that excuses *token*, or ``None`` when it is a defect.

    Order matters only for reporting: the cheapest structural rules (keypath)
    run before the textual ones, and the subprocess call runs last.
    """
    if any("legacy_path" in part for part in keypath):
        return EXCLUSION_PROVENANCE
    if any(part in _ILLUSTRATIVE_KEYS for part in keypath):
        return EXCLUSION_ILLUSTRATIVE
    if _FORMULA.search(text):
        return EXCLUSION_FORMULA
    if _negated(text, token) or _EXCLUSION_HEADER.search(text):
        return EXCLUSION_EXCLUDED_MECHANISM
    if _conditional(text, token):
        return EXCLUSION_CONDITIONAL
    if _declared_retired(text, token):
        return EXCLUSION_HISTORICAL
    if _git_ignored(repo_root, token):
        return EXCLUSION_GITIGNORED
    return None


# ---------------------------------------------------------------------------
# Walker
# ---------------------------------------------------------------------------
def _walk_strings(node, path: Tuple[str, ...] = ()) -> Iterator[Tuple[Tuple[str, ...], str]]:
    """Yield ``(keypath, string)`` for every string in a parsed node."""
    if isinstance(node, dict):
        for key, value in node.items():
            yield from _walk_strings(value, path + (str(key),))
    elif isinstance(node, list):
        for value in node:
            yield from _walk_strings(value, path + ("[]",))
    elif isinstance(node, str):
        yield path, node


def node_files(repo_root: Path) -> List[Path]:
    """Every single-node convention file, at the settled measurement's scope."""
    root = Path(repo_root) / "src" / "atdd"
    return sorted(root.glob("*/conventions/nodes/*.convention.yaml"))


def scan_node(path: Path, data: dict, repo_root: Path) -> List[Finding]:
    """Every unfollowable remedy in one parsed convention node."""
    node_id = str(data.get("rule_id") or path.stem)
    findings: List[Finding] = []
    for keypath, text in _walk_strings(data):
        is_provenance = any("legacy_path" in part for part in keypath)
        is_illustrative = any(part in _ILLUSTRATIVE_KEYS for part in keypath)
        operative = bool(keypath) and keypath[-1] in OPERATIVE_KEYS

        # A retired verb is unfollowable wherever a reader is told to run it.
        if not (is_provenance or is_illustrative):
            for verb, retired in RETIRED_VERBS.items():
                if verb in text and not verb_documented_as_retired(text, verb):
                    findings.append(
                        Finding(
                            node_id=node_id,
                            node_path=path,
                            keypath=".".join(keypath),
                            token=verb,
                            kind=KIND_RETIRED_VERB,
                            detail=(
                                f"{retired.reason}. Use {retired.replacement}"
                            ),
                        )
                    )

        if not operative:
            continue
        for token in path_tokens(text):
            if (Path(repo_root) / token).exists():
                continue
            excuse = classify(keypath, text, token, repo_root)
            if excuse is not None:
                continue
            findings.append(
                Finding(
                    node_id=node_id,
                    node_path=path,
                    keypath=".".join(keypath),
                    token=token,
                    kind=KIND_ABSENT_PATH,
                    detail=(
                        f"the prose names {token!r}, which is not in the repo; "
                        f"correct the path or drop the pointer"
                    ),
                )
            )
    return findings


def scan_nodes(repo_root: Path) -> List[Finding]:
    """Every unfollowable remedy across every convention node."""
    findings: List[Finding] = []
    for path in node_files(repo_root):
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            continue
        if not isinstance(data, dict):
            continue
        findings.extend(scan_node(path, data, repo_root))
    return findings
