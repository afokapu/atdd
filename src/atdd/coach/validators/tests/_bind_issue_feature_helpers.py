"""Shared harness for the #1635 issue↔feature binding RED tests.

Every helper builds a REAL State Store on a tmp path and a REAL ``plan/`` tree
on disk. The acceptances under test are about what actually lands in
``objects.data.feature`` and what actually resolves out of ``plan/``, so the
store and the plan tree are never mocked — mirrors
``atdd.state.tests._agent_session_helpers``.

RED-phase note: nothing here imports the unwritten surfaces (the backfill
entry point, the C011 validator, the L003 resolver). Those are resolved
dynamically inside the tests via :func:`optional_attr` so that a missing
surface fails as a *behavioural assertion* naming what is absent, never as a
collection-time ``ImportError`` — a collection error would make the suite red
for the wrong reason and would mask the real gap once it is closed.
"""
from __future__ import annotations

import importlib
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from atdd.state.db import connect, init_state_store
from atdd.state.manifest_import import GITHUB_PROVIDER, WORK_ITEM_KIND
from atdd.state.store import StateStore

ISSUE_REF_KIND = "issue"

# The feature this issue authored, and the WMBT its YAML declares.
FEATURE_URN = "feature:govern-lifecycle:bind-issue-feature"
FEATURE_WMBT = "wmbt:govern-lifecycle:Y006"

# The two WMBTs of the #1735 observation, kept by their real codes so the
# fixture and the incident read as the same thing: C020 was authored by the
# issue's own commit and the banner omitted it; C021 lives only on a sibling
# branch and the banner listed it as the issue's.
ISSUE_BRANCH_WMBT = "wmbt:govern-lifecycle:C020"
SIBLING_BRANCH_WMBT = "wmbt:govern-lifecycle:C021"

# A well-formed feature URN that resolves to nothing in plan/.
ABSENT_FEATURE_URN = "feature:govern-lifecycle:no-such-feature-exists"

# A train identity wearing a feature's clothes — the drift measured on #1626.
TRAIN_URN_IN_FEATURE_SLOT = "train:issue-lifecycle:drive-state-machine"


def control_root(tmp_path: Path) -> Path:
    """A directory the State Store will accept as a control root."""
    (tmp_path / ".atdd").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".atdd" / "config.yaml").write_text("version: '1.0'\n", encoding="utf-8")
    return tmp_path


def open_store(root: Path) -> StateStore:
    return StateStore(connect(init_state_store(start=root)))


def seed_issue(
    store: StateStore,
    *,
    slug: str,
    issue_number: int,
    state: str = "PLANNED",
    feature: Optional[str] = None,
    body: str = "",
    extra: Optional[Dict[str, Any]] = None,
) -> str:
    """A work item linked to its github issue, as the real mint leaves it.

    ``feature=None`` reproduces the measured status quo: 638 of 808 live work
    items carry no feature at all.
    """
    data: Dict[str, Any] = {
        "title": slug,
        "type": "bug",
        "branch": f"feat/{slug}",
        "train": TRAIN_URN_IN_FEATURE_SLOT,
        "feature": feature,
        "body": body,
    }
    data.update(extra or {})
    store.objects.upsert(slug, WORK_ITEM_KIND, state=state, data=data)
    store.external_refs.link(slug, GITHUB_PROVIDER, ISSUE_REF_KIND, str(issue_number))
    return slug


def read_issue_data(store: StateStore, issue_number: int) -> Dict[str, Any]:
    """The stored work item's ``data`` for a github issue number."""
    ref = store.external_refs.resolve(GITHUB_PROVIDER, ISSUE_REF_KIND, str(issue_number))
    assert ref is not None, f"github issue #{issue_number} is not registered in the store"
    obj = store.objects.get(ref.object_uid)
    assert obj is not None, f"work item {ref.object_uid!r} is missing from the store"
    return dict(obj.data or {})


def write_plan_tree(root: Path, *, wmbts=(FEATURE_WMBT,)) -> Path:
    """A minimal but real ``plan/`` tree carrying one resolvable feature.

    Mirrors the on-disk shape the planner authors: the feature YAML lives at
    ``plan/<wagon_dir>/features/<name>.yaml`` and declares its ``wmbts:`` list.
    """
    import yaml

    features = root / "plan" / "govern_lifecycle" / "features"
    features.mkdir(parents=True, exist_ok=True)
    doc = {
        "urn": FEATURE_URN,
        "wagon": "wagon:govern-lifecycle",
        "description": "The issue↔feature binding under test.",
        "sizing": {"wmbts": len(wmbts), "footprint_score": 1, "footprint_size": "XS"},
        "wmbts": list(wmbts),
        "components": {"backend": {"application": [
            {"type": "use_cases", "count": 1, "rationale": "the binding under test"},
        ]}},
    }
    path = features / "bind_issue_feature.yaml"
    path.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
    return path


def git(root: Path, *args: str) -> subprocess.CompletedProcess:
    """Run git in *root*, raising with its stderr when it fails."""
    proc = subprocess.run(
        ["git", *args], cwd=str(root), capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode == 0, f"git {' '.join(args)} failed: {proc.stderr}"
    return proc


def make_two_worktree_repo(
    tmp_path: Path, *, issue_branch: str, sibling_branch: str = "feat/somewhere-else"
) -> Tuple[Path, Path]:
    """A REAL git repo with two REAL worktrees on two different branches.

    Returns ``(sibling, issue_tree)``: the checkout an operator happens to be
    standing in, and the one holding ``issue_branch``. Both carry ``.atdd/``,
    because ``.atdd/config.yaml`` is a tracked file and a git worktree therefore
    gets one — which is exactly why resolving from cwd looked plausible.

    Two real worktrees rather than two directories: the resolution under test
    reads ``git worktree list --porcelain``, so a pair of ordinary directories
    would be resolvable by no mechanism and the test would pass for the wrong
    reason.
    """
    sibling = control_root(tmp_path / "sibling")
    git(sibling, "init", "-q", "-b", sibling_branch)
    git(sibling, "config", "user.email", "harness@atdd.test")
    git(sibling, "config", "user.name", "harness")
    git(sibling, "add", "-A")
    git(sibling, "commit", "-q", "-m", "seed")

    issue_tree = tmp_path / "issue-tree"
    git(sibling, "worktree", "add", "-q", "-b", issue_branch, str(issue_tree))
    return sibling, issue_tree


def write_stub_gh(root: Path, issues: Dict[int, Dict[str, Any]]) -> Path:
    """A real `gh` on PATH that answers issue views and returns NO wmbt labels.

    The discriminator for the plan-backed lookup. GitHub is reachable and the
    issue fetch succeeds, so `atdd coach enter` gets past its metadata read —
    but ``gh issue list --label atdd-wmbt`` returns ``[]``, which is the honest
    live answer (nothing has minted that label since #1477; the newest such
    issue is #1059).

    Any WMBT that appears in the output therefore came from ``plan/`` and from
    nowhere else. Making the provider merely *absent* would not prove this: the
    old lookup swallows subprocess failure and returns an empty list, so an
    absent provider is indistinguishable from a correct empty answer.
    """
    import json as _json

    bindir = root / "stub-bin"
    bindir.mkdir(parents=True, exist_ok=True)
    script = bindir / "gh"
    script.write_text(
        "#!/usr/bin/env python3\n"
        "import json, sys\n"
        f"ISSUES = {_json.dumps({str(k): v for k, v in issues.items()})}\n"
        "argv = sys.argv[1:]\n"
        "if 'list' in argv:\n"
        "    print('[]')            # no atdd-wmbt issues exist — the live truth\n"
        "    sys.exit(0)\n"
        "if 'view' in argv:\n"
        "    for a in argv:\n"
        "        if a in ISSUES:\n"
        "            print(json.dumps(ISSUES[a])); sys.exit(0)\n"
        "    sys.exit(1)\n"
        "print('{}')\n",
        encoding="utf-8",
    )
    script.chmod(0o755)

    config = root / ".atdd" / "config.yaml"
    config.write_text(
        "version: '1.0'\ngithub:\n  repo: atdd-test/atdd-test\n", encoding="utf-8"
    )
    return bindir


def stub_issue(number: int, *, body: str = "", status: str = "PLANNED") -> Dict[str, Any]:
    """The shape `IssueLifecycle._fetch_issue` expects back from `gh issue view`."""
    return {
        "number": number,
        "title": f"probe issue {number}",
        "state": "OPEN",
        "labels": [{"name": "atdd-issue"}, {"name": f"atdd:{status}"}],
        "body": body,
    }


def optional_attr(module_path: str, attr: str) -> Any:
    """Return ``module_path.attr``, or ``None`` when either does not exist yet.

    The RED-phase escape hatch: the caller asserts on the ``None`` with a
    message naming the missing surface, so an unwritten seam reads as a
    behavioural failure rather than an import error at collection time.
    """
    try:
        module = importlib.import_module(module_path)
    except ImportError:
        return None
    return getattr(module, attr, None)


def source_of(module_path: str) -> str:
    """The on-disk source text of an importable module (for anchor scans)."""
    module = importlib.import_module(module_path)
    return Path(module.__file__).read_text(encoding="utf-8")
