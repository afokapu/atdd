# Phase: RED
# Layer: unit
# Assertion: behavioral
"""#1965 — a convention node's remedy must be followable.

A ``fix_hint`` is the one part of a rule an operator reads *while blocked*. When
it names a file that is not there, or a CLI verb that no longer exists, the rule
has told them to do something impossible at the exact moment they are stuck.
Nothing reads a ``fix_hint``, so when #1303 removed ``atdd issue`` and the
smoke-acceptance validator was renamed, every hint quoting them stayed as
written.

**The measurement is the design.** A naive scan of all 316 convention nodes
finds 179 of 332 concrete repo paths absent from disk — 30x the real defect
count, and a rule shipped against it would have needed 173 exceptions. The count
only becomes an obligation once it is decomposed by cause: 137 are
``source.legacy_path`` provenance (a historical record, carrying a
``legacy_sha``, naming a monolith that was deliberately deleted — pointing at a
deleted file is what provenance IS), 34 are illustrative example paths
(fictional by design), and 22 are operative prose. Of those 22 (14 distinct),
six are real.

So these tests are mostly about what the rule must NOT fire on. Every exclusion
below is a way the naive scan was wrong, and each is pinned here so the rule
cannot be "fixed" later by quietly widening it. Two are worth the reader's time:

*The gitignored-runtime rule asks git.* ``.atdd/runtime/``,
``.atdd/state/state.sqlite`` and ``.atdd/smoke-evidence/`` exist in a full
checkout and are absent from a worktree because they are gitignored runtime
state. ``git check-ignore`` separates exactly those three from every other
candidate, which a hardcoded list would also do — until the first time a runtime
path moves, after which the list excuses a path that has become a real defect.

*The historical-record rule keys on tense.* This is the sharpest distinction in
the whole rule, because the same file-shaped token is a defect in one node and
deliberate in another. ``coach.execution.atomic-registry-write`` says #1270
"**retired** the ``.atdd/manifest.yaml`` mirror" — past tense, explicitly marked
retired, a record of what used to be. ``coach.lifecycle.no-terminal-before-
lifecycle-satisfied`` says the phase labels "**live under** ``.atdd/labels.yaml``"
— present tense, a pointer, and the file is not there. If the exclusion keyed on
the token instead of the tense, it would excuse the very defect this issue
exists to catch.

RED: every import below resolves to nothing —
``atdd.planner.validators.remedy_followability`` does not exist yet. The node
stays unbound until GREEN, because ``bind_rule`` enforces a bidirectional
contract (``rule-id.convention.yaml::rule_schema.conditional``: a validator is
REQUIRED when disposition is ``strict`` and FORBIDDEN when
``documentation-only``), so the node and its validator are one indivisible unit
that cannot land in separate commits.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from atdd.coach.utils.repo import find_repo_root
from atdd.planner.validators.remedy_followability import (
    EXCLUSION_CONDITIONAL,
    EXCLUSION_EXCLUDED_MECHANISM,
    EXCLUSION_FORMULA,
    EXCLUSION_GITIGNORED,
    EXCLUSION_HISTORICAL,
    EXCLUSION_ILLUSTRATIVE,
    EXCLUSION_PROVENANCE,
    KIND_ABSENT_PATH,
    KIND_RETIRED_VERB,
    RETIRED_VERBS,
    classify,
    path_tokens,
    verb_documented_as_retired,
    scan_node,
    scan_nodes,
)

# `platform`: this module is a toolkit-self test and cannot run in a consumer
# repo. Two of its assertions say so concretely — the gitignored-runtime case
# reads THIS repo's `.gitignore` via `git check-ignore`, and the corpus case
# globs THIS repo's convention nodes (in a consumer repo it would glob an empty
# set and pass vacuously, which is worse than failing). Flagged as advisory by
# `coach.source-layout.toolkit-path-string-in-unmarked-selftest` on the first
# push, and the flag was right.
pytestmark = [pytest.mark.planner, pytest.mark.platform]

_ROOT = Path(find_repo_root(Path(__file__)))


# ---------------------------------------------------------------------------
# The tokenizer. Four of the naive scan's 14 candidates were never paths.
# ---------------------------------------------------------------------------
def test_a_prose_disjunction_is_not_a_path():
    """`tests/ADRs` and `plan/test/code` use the slash to mean "or".

    "an implementation decision, reframed to the job it serves or routed to
    tests/ADRs" means *tests or ADRs*; "the plan/test/code themes align to the
    planner/tester/coder archetypes" enumerates three themes. Neither ends in a
    file extension or a `/`, which is what separates a pointer from a phrase.
    """
    assert path_tokens("or routed to tests/ADRs.") == []
    assert path_tokens("The plan/test/code themes align to planner/tester/coder") == []


def test_a_placeholder_path_is_not_a_path_even_truncated():
    """The lab's tokenizer stopped its charset at `<`, so it emitted
    `src/atdd/planner/conventions/nodes/planner` — a truncation that defeated
    its own placeholder guard, because the `<` it would have rejected had
    already been cut off. The charset must ADMIT the placeholder characters in
    order to reject them.
    """
    text = ("src/atdd/planner/conventions/nodes/"
            "planner.<artifact>.definition.convention.yaml")
    assert path_tokens(text) == []
    assert path_tokens("contracts/{domain}/{resource}/tests/") == []
    assert path_tokens("src/atdd/*/validators/") == []


def test_a_real_pointer_is_tokenized():
    """The positive case, so the tests above cannot pass by tokenizing nothing."""
    assert path_tokens(
        "re-run it (pytest src/atdd/planner/validators/test_x.py -v)."
    ) == ["src/atdd/planner/validators/test_x.py"]
    assert path_tokens("state lives under .atdd/runtime/ and is gitignored") == [
        ".atdd/runtime/"
    ]


# ---------------------------------------------------------------------------
# The exclusions. Each is a way the naive count of 179 was wrong.
# ---------------------------------------------------------------------------
def test_provenance_is_excluded():
    """137 of the 179. `source.legacy_path` records where a node was extracted
    from and carries a `legacy_sha` beside it; the monolith it names was
    deliberately deleted. Gating it would force 137 suppressions and destroy the
    record of where every node came from (issue Decision #2).
    """
    assert classify(
        keypath=("source", "legacy_path"),
        text="src/atdd/planner/conventions/acceptance.convention.yaml",
        token="src/atdd/planner/conventions/acceptance.convention.yaml",
        repo_root=_ROOT,
    ) == EXCLUSION_PROVENANCE


def test_illustrative_example_paths_are_excluded():
    """34 of the 179. `contracts/commons/WRONG/uuid.schema.json` is fictional on
    purpose — it is the negative example of a naming rule. A rule that demanded
    it exist would demand the repo contain its own counter-examples.
    """
    assert classify(
        keypath=("terms", "[]", "examples", "negative", "[]"),
        text="contracts/commons/WRONG/uuid.schema.json",
        token="contracts/commons/WRONG/uuid.schema.json",
        repo_root=_ROOT,
    ) == EXCLUSION_ILLUSTRATIVE


def test_a_schematic_formula_is_excluded():
    """`contracts/theme/seg1/seg2/aspect/variant.schema.json` sits in
    `operational_guidance`, not in an `examples:` block, so a key-based
    classifier mis-buckets it as operative — this is the one the lab's cause
    split got wrong. It is the right-hand side of "Formula: artifact
    theme:seg1:seg2:aspect.variant -> ...": a template, whose `seg1`/`seg2` are
    positions rather than directories. Excluding it at its cause is what keeps
    this from becoming a named-token exception.
    """
    assert classify(
        keypath=("content", "operational_guidance"),
        text=("Formula: artifact theme:seg1:seg2:aspect.variant -> "
              "contracts/theme/seg1/seg2/aspect/variant.schema.json."),
        token="contracts/theme/seg1/seg2/aspect/variant.schema.json",
        repo_root=_ROOT,
    ) == EXCLUSION_FORMULA


def test_an_excluded_mechanism_is_excluded():
    """`plan/_meta.yaml` in `planner.decomposition.local-scope` appears in a list
    of mechanisms the protocol does NOT use: "What is NOT in this protocol: no
    atdd agent ask, no step-1 disk persistence, no plan/_meta.yaml". Its absence
    from disk is the rule HOLDING, not failing — the one case where flagging the
    path would invert the node's meaning.
    """
    assert classify(
        keypath=("statement",),
        text=("What is NOT in this protocol: no atdd agent ask, no step-1 disk "
              "persistence, no plan/_meta.yaml, no coach involvement."),
        token="plan/_meta.yaml",
        repo_root=_ROOT,
    ) == EXCLUSION_EXCLUDED_MECHANISM
    assert classify(
        keypath=("terms", "[]", "text"),
        text=("excluded mechanisms: atdd-agent-ask, step-1 disk persistence, "
              "plan/_meta.yaml, coach involvement."),
        token="plan/_meta.yaml",
        repo_root=_ROOT,
    ) == EXCLUSION_EXCLUDED_MECHANISM


def test_a_conditional_reference_is_excluded():
    """`telemetry/_tracking_manifest.yaml` is guarded: the node's own statement
    is "Tracking manifest must be complete **if present**". A conditional is a
    predicate subject, not a pointer — the node never tells anyone to go open it.
    """
    assert classify(
        keypath=("content", "normative_text"),
        text=("If telemetry/_tracking_manifest.yaml exists, all signals must be "
              "present"),
        token="telemetry/_tracking_manifest.yaml",
        repo_root=_ROOT,
    ) == EXCLUSION_CONDITIONAL
    assert classify(
        keypath=("terms", "[]", "text"),
        text=("telemetry/_tracking_manifest.yaml; when present it must list "
              "every telemetry signal as a file."),
        token="telemetry/_tracking_manifest.yaml",
        repo_root=_ROOT,
    ) == EXCLUSION_CONDITIONAL


def test_gitignored_runtime_state_is_excluded_and_git_is_the_oracle():
    """These three exist in a full checkout and are absent from a worktree
    purely because they are gitignored runtime state. Asking `git check-ignore`
    rather than hardcoding them means the exclusion cannot outlive the paths: if
    a runtime path is moved out of `.gitignore` tomorrow, it stops being excused
    the same day, whereas a literal list would keep excusing it.
    """
    for token in (".atdd/runtime/", ".atdd/state/state.sqlite",
                  ".atdd/smoke-evidence/"):
        assert classify(
            keypath=("content", "fix_hint"),
            text=f"runtime state lives under {token}",
            token=token,
            repo_root=_ROOT,
        ) == EXCLUSION_GITIGNORED, token


def test_a_path_declared_retired_is_excluded_but_a_present_tense_pointer_is_not():
    """The tense test, and the sharpest line in the rule.

    Both nodes name a file under `.atdd/` that is not on disk. One is a record,
    one is a defect, and only the grammar of the sentence tells them apart. An
    exclusion keyed on the token would excuse both — including defect #3, which
    is the whole reason this rule exists.
    """
    # A record: past tense, explicitly marked retired.
    assert classify(
        keypath=("statement",),
        text=("(#1270 Slice G retired the `.atdd/manifest.yaml` mirror this "
              "principle was first extracted from; the State Store is now the "
              "sole registry it governs.)"),
        token=".atdd/manifest.yaml",
        repo_root=_ROOT,
    ) == EXCLUSION_HISTORICAL

    # A defect: present tense, a pointer, and the file is not there.
    assert classify(
        keypath=("content", "fix_hint"),
        text="for atdd the phase labels live under .atdd/labels.yaml",
        token=".atdd/labels.yaml",
        repo_root=_ROOT,
    ) is None


def test_an_absent_operative_path_is_not_excluded():
    """The load-bearing negative: with six exclusion rules in play, the rule must
    still fire on a plain dangling pointer. Without this, every test above could
    pass by excluding everything.
    """
    assert classify(
        keypath=("content", "fix_hint"),
        text=("Re-run the validator to confirm clean (pytest "
              "src/atdd/planner/validators/test_wmbt_has_smoke_acceptance.py -v)."),
        token="src/atdd/planner/validators/test_wmbt_has_smoke_acceptance.py",
        repo_root=_ROOT,
    ) is None


# ---------------------------------------------------------------------------
# Retired verbs. #1303 removed `atdd issue`; two nodes still instruct it.
# ---------------------------------------------------------------------------
def test_the_retired_verb_table_names_its_replacement():
    """A remedy that says only "that verb is gone" is itself unfollowable. Each
    retired verb carries the live verb that replaced it, both confirmed by the
    CLI's own help: `atdd coach issues` is "the coach-archetype replacement for
    `atdd issue open` / `atdd issue <N>`", and `atdd coach transition` is
    "...replacement for `atdd issue <N> --status <TO>`".
    """
    assert "atdd issue " in RETIRED_VERBS
    entry = RETIRED_VERBS["atdd issue "]
    assert "atdd coach transition" in entry.replacement
    assert "1303" in entry.reason


def test_a_verb_named_only_to_document_its_retirement_is_not_an_instruction():
    """A rule about retired verbs must be able to NAME one to say what replaced it.

    `planner.convention.remedy-must-be-followable` convicted itself the moment
    it was authored: its own fix_hint says "`atdd issue <N> --status <PHASE>`
    became `atdd coach transition <N> <PHASE>`", which is the remedy, not an
    instruction to run the dead verb. This is the verb-side of the tense test
    the path rule already applies — and it is the same principle, because a
    rule that cannot describe its own remedy cannot be followed either.
    """
    assert verb_documented_as_retired(
        "For a retired verb: replace it with the live one — `atdd issue <N> "
        "--status <PHASE>` became `atdd coach transition <N> <PHASE>`, and "
        "`atdd issue open` became `atdd coach issues open`.",
        "atdd issue ",
    )


def test_one_instructional_mention_defeats_the_documentation_excuse():
    """`all`, not `any` — the loophole this rule would otherwise open.

    A node could otherwise explain the replacement in one breath and still tell
    the reader to run the dead verb in the next, and the retirement prose would
    excuse the instruction. Here the first mention is documented and the second
    is a live instruction; the node is NOT excused.
    """
    assert not verb_documented_as_retired(
        "`atdd issue open` was removed in #1303. To list issues, run "
        "atdd issue open and read the table.",
        "atdd issue ",
    )
    # And the two real defects stay defects: neither carries a marker at all.
    assert not verb_documented_as_retired(
        "atdd issue <issue> --status SMOKE", "atdd issue "
    )
    assert not verb_documented_as_retired(
        "or mint one from the main job (run `atdd issue open` to list "
        "bindable issue slugs).",
        "atdd issue ",
    )


# ---------------------------------------------------------------------------
# The corpus. The rule is `strict` at zero, which is only affordable at n=6.
# ---------------------------------------------------------------------------
def test_the_corpus_carries_no_unfollowable_remedy():
    """The obligation itself, over all 316 nodes.

    This is what #1958 and #1943 could not have: both found a defect whose
    remedy was unaffordable (369 of 473, and 101 of 229) and had to settle for
    `advisory` — a rule that logs a defect instead of refusing it. Six is
    affordable, so this gates.

    Fails in RED with the six known defects, and is the assertion that proves
    the repairs landed.
    """
    findings = scan_nodes(_ROOT)
    assert findings == [], (
        f"{len(findings)} unfollowable remedies:\n" +
        "\n".join(f"  [{f.kind}] {f.node_id}: {f.token} ({f.keypath})"
                  for f in findings)
    )


def test_each_of_the_six_defect_shapes_is_detected():
    """The census the issue measured, pinned as DETECTION rather than as repo state.

    An earlier draft of this test asserted the six defects were present in the
    live corpus. That pinned the census, but it could only pass before the
    repair — the assertion and `test_the_corpus_carries_no_unfollowable_remedy`
    are each other's inverse, so one of them had to be wrong after GREEN. What
    is worth holding forever is not that the repo still contains the defects,
    but that the scanner still catches their shapes: if someone reintroduces
    `.atdd/labels.yaml` or an `atdd issue` instruction tomorrow, this is what
    notices.

    So each case feeds the ORIGINAL prose through the scanner on a synthetic
    node. The repo-state half of the obligation is held by the corpus test.

    `tests/platform_validation/` is the sixth defect, which the issue's verdict
    table does not adjudicate: `planner.interface.tests-subdirectory` sent the
    reader to a directory that exists nowhere, to run two test functions that
    exist nowhere either, when ONE validator covers both leaf rules
    (`_ROOTS = ("contracts", "telemetry")`).
    """
    cases = [
        # (node_id, prose key, the original prose, token, kind)
        ("planner.acceptance.authoring-guidelines", "operational_guidance",
         "metric_binding: one metric_id from plan/_lego/acceptance-metrics.yaml "
         "(no mixed measures).",
         "plan/_lego/acceptance-metrics.yaml", KIND_ABSENT_PATH),
        ("planner.wmbt.must-have-smoke-acceptance", "fix_hint",
         "4. Re-run the validator to confirm clean (pytest "
         "src/atdd/planner/validators/test_wmbt_has_smoke_acceptance.py -v).",
         "src/atdd/planner/validators/test_wmbt_has_smoke_acceptance.py",
         KIND_ABSENT_PATH),
        ("coach.lifecycle.no-terminal-before-lifecycle-satisfied", "fix_hint",
         "for atdd the phase labels live under .atdd/labels.yaml):",
         ".atdd/labels.yaml", KIND_ABSENT_PATH),
        ("coach.lifecycle.no-terminal-before-lifecycle-satisfied", "fix_hint",
         "atdd issue <issue> --status SMOKE",
         "atdd issue ", KIND_RETIRED_VERB),
        ("planner.plan.confirm-binds-an-issue", "fix_hint",
         "or mint one from the main job (run `atdd issue open` to list "
         "bindable issue slugs).",
         "atdd issue ", KIND_RETIRED_VERB),
        ("planner.interface.tests-subdirectory", "text",
         "Enforcement lives in platform validation tests under "
         "tests/platform_validation/.",
         "tests/platform_validation/", KIND_ABSENT_PATH),
    ]

    for node_id, key, prose, token, kind in cases:
        node = {"rule_id": node_id, "content": {key: prose}}
        found = {
            (f.token, f.kind)
            for f in scan_node(Path(f"{node_id}.convention.yaml"), node, _ROOT)
        }
        assert (token, kind) in found, (
            f"{node_id}: {token!r} ({kind}) not detected in {prose!r}; got {found}"
        )
