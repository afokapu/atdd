#!/usr/bin/env python3
"""#2024 — does `projection_at` answer the cutover criterion's question safely?

Run from a checkout:  PYTHONPATH=src python3 docs/spikes/labs/2024-projection-at-byte-exactness/probe.py

Two properties are under test, because `_projection_criterion` (cutover.py:121) needs both:

  (a) on a repo where the projection does not exist at HEAD it must report "no projection"
      rather than crash — the criterion's job there is to return `unmet`;
  (b) it must be byte-exact, because the claim it stamps (cutover.py:49-51) is
      "project(hydrate(p)) == p, byte for byte, over the projection at HEAD".

Result when this was written, against origin/main @ 5529abf4: (a) holds for both
`gitstore.projection_at` and `merge_authority.projection_at` except that the latter raises
on a commit-less repo; (b) FAILS for `gitstore.projection_at` — `text=True` normalises
CRLF to LF, which turns a non-canonical commit into a passing one. A bytes reader holds
for both.
"""
import shutil
import subprocess
import tempfile
from pathlib import Path

from atdd.state import cutover, gitstore
from atdd.state import merge_authority as ma
from atdd.state.db import connect, init_state_store
from atdd.state.identity import mint_uid
from atdd.state.projection import PROJECTION_RELATIVE, PROJECTION_SUFFIX, project
from atdd.state.store import StateStore
from atdd.state.store_migration import WORK_ITEM_KIND

PROJ = PROJECTION_RELATIVE.as_posix()


def git(repo, *args):
    return subprocess.run(["git", *args], cwd=repo, capture_output=True)


def newrepo(name):
    repo = Path(tempfile.mkdtemp(prefix="probe2024-")) / name
    repo.mkdir(parents=True)
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.email", "probe@example.com")
    git(repo, "config", "user.name", "probe")
    git(repo, "config", "core.autocrlf", "false")  # pin: the probe is about bytes
    return repo


def commit(repo, message):
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "--no-verify", "-m", message)


def projection_bytes_at(repo, commit_ish):
    """The candidate reader: gitstore's git calls, binary pipes, bytes out."""
    listing = subprocess.run(
        ["git", "ls-tree", "--name-only", f"{commit_ish}:{PROJ}"],
        cwd=repo, capture_output=True,  # deliberately no text=True
    )
    if listing.returncode != 0:
        return {}  # the commit predates the projection directory
    names = [
        n for n in listing.stdout.decode("utf-8", "surrogateescape").splitlines()
        if n.endswith(PROJECTION_SUFFIX)
    ]
    return {
        name: subprocess.run(
            ["git", "show", f"{commit_ish}:{PROJ}/{name}"], cwd=repo, capture_output=True,
        ).stdout
        for name in sorted(names)
    }


def build_cases():
    cases = {}

    repo = newrepo("no-projection-ever")
    (repo / "README.md").write_text("x\n")
    commit(repo, "init")
    cases["no-projection-ever"] = repo

    # The defect-3 case: on disk, never committed.
    repo = newrepo("uncommitted-projection")
    (repo / "README.md").write_text("x\n")
    commit(repo, "init")
    directory = repo / PROJECTION_RELATIVE
    directory.mkdir(parents=True)
    (directory / "wi_A.yaml").write_text("uid: wi_A\nslug: thing\n")
    cases["uncommitted-projection"] = repo

    repo = newrepo("committed-projection")
    directory = repo / PROJECTION_RELATIVE
    directory.mkdir(parents=True)
    (directory / "wi_A.yaml").write_text("uid: wi_A\nslug: thing\n")
    (directory / "wi_B.yaml").write_text("uid: wi_B\nslug: other\n")
    commit(repo, "init with projection")
    cases["committed-projection"] = repo

    # A checkout with no commits is a legitimate cold start (reconcile.resolve_head).
    cases["no-head"] = newrepo("no-head")

    repo = newrepo("committed-then-deleted")
    directory = repo / PROJECTION_RELATIVE
    directory.mkdir(parents=True)
    (directory / "wi_A.yaml").write_text("uid: wi_A\nslug: thing\n")
    commit(repo, "add projection")
    shutil.rmtree(directory)
    commit(repo, "remove projection")
    cases["committed-then-deleted"] = repo

    repo = newrepo("committed-non-mapping")
    directory = repo / PROJECTION_RELATIVE
    directory.mkdir(parents=True)
    (directory / "wi_A.yaml").write_text("- just\n- a list\n")
    commit(repo, "init")
    cases["committed-non-mapping"] = repo

    for name, blob in (
        ("committed-crlf", b"uid: wi_CRLF\r\nslug: windows\r\n"),
        ("committed-lone-cr", b"uid: wi_CR\rslug: oldmac\r"),
        ("committed-non-utf8", b"uid: wi_BAD\nslug: \xff\xfe-not-utf8\n"),
        ("committed-no-trailing-newline", b"uid: wi_NONL\nslug: no-trailing-newline"),
    ):
        repo = newrepo(name)
        directory = repo / PROJECTION_RELATIVE
        directory.mkdir(parents=True)
        (directory / "wi_X.yaml").write_bytes(blob)
        commit(repo, "init")
        cases[name] = repo

    return cases


def call(fn, *args):
    try:
        value = fn(*args)
        return f"OK {len(value)} file(s)"
    except Exception as exc:  # the point of the probe is which of these explode
        return f"RAISE {type(exc).__name__}"


def main():
    cases = build_cases()

    print("(a) does it report 'no projection' rather than crash?\n")
    header = f"{'case':<32}{'gitstore':<24}{'merge_authority':<26}bytes reader"
    print(header)
    print("-" * len(header))
    for name, repo in cases.items():
        print(
            f"{name:<32}"
            f"{call(gitstore.projection_at, repo, 'HEAD'):<24}"
            f"{call(ma.projection_at, repo, 'HEAD'):<26}"
            f"{call(projection_bytes_at, repo, 'HEAD')}"
        )

    print("\n(b) is it byte-exact against the committed blob?\n")
    header = f"{'case':<32}{'gitstore':<24}bytes reader"
    print(header)
    print("-" * len(header))
    for name in (
        "committed-crlf", "committed-lone-cr",
        "committed-non-utf8", "committed-no-trailing-newline",
    ):
        repo = cases[name]
        true_blob = git(repo, "show", f"HEAD:{PROJ}/wi_X.yaml").stdout
        try:
            text = gitstore.projection_at(repo, "HEAD")["wi_X.yaml"]
            via_text = "exact" if text.encode("utf-8") == true_blob else "MANGLED"
        except Exception as exc:
            via_text = type(exc).__name__
        via_bytes = "exact" if projection_bytes_at(repo, "HEAD")["wi_X.yaml"] == true_blob else "MANGLED"
        print(f"{name:<32}{via_text:<24}{via_bytes}")

    print("\n(c) the consequence — a CRLF commit is not canonical, but text=True says it is\n")
    repo = cases["committed-crlf"]
    true_blob = git(repo, "show", f"HEAD:{PROJ}/wi_X.yaml").stdout
    canonical_lf = b"uid: wi_CRLF\nslug: windows\n"  # what project() would emit
    text_read = gitstore.projection_at(repo, "HEAD")["wi_X.yaml"].encode("utf-8")
    print(f"  true committed blob == canonical LF ? {true_blob == canonical_lf}"
          "   <- the honest verdict: NOT canonical")
    print(f"  text-read blob      == canonical LF ? {text_read == canonical_lf}"
          "   <- what the criterion would conclude")
    verdict = "FALSE PASS" if (text_read == canonical_lf and true_blob != canonical_lf) else "no divergence"
    print(f"  => {verdict}")


def from_flag_bypasses_head():
    """`cutover --from` passes any directory through, so fixing the default is not enough.

    migrate_cli.py:280 forwards args.from_dir straight into cutover.check, and
    _projection_criterion (cutover.py:120) treats whatever it is handed as authoritative.
    """
    print("\n" + "=" * 78)
    print("(d) the --from bypass: can an UNCOMMITTED directory still earn a pass?")
    print("=" * 78)
    base = Path(tempfile.mkdtemp(prefix="frombypass-"))
    repo = base / "repo"
    (repo / ".atdd" / "state").mkdir(parents=True)
    (repo / ".atdd" / "config.yaml").write_text("{}\n")
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, capture_output=True)
    for key, value in (("user.email", "probe@example.com"), ("user.name", "probe")):
        subprocess.run(["git", "config", key, value], cwd=repo, capture_output=True)
    (repo / "README.md").write_text("x\n")
    subprocess.run(["git", "add", "-A"], cwd=repo, capture_output=True)
    subprocess.run(["git", "commit", "-q", "--no-verify", "-m", "init"],
                   cwd=repo, capture_output=True)

    db = init_state_store(start=repo)
    conn = connect(db)
    store = StateStore(conn)
    for i in range(3):
        store.objects.upsert(mint_uid(), WORK_ITEM_KIND, state="PLANNED",
                             data={"title": f"item {i}", "slug": f"thing-{i}",
                                   "owner_actor": "someone"})
    # A canonical projection, written OUTSIDE the repository entirely.
    elsewhere = base / "outside-the-repo"
    result = project(store, elsewhere)
    conn.close()

    committed = subprocess.run(
        ["git", "ls-tree", "--name-only", "HEAD:" + PROJECTION_RELATIVE.as_posix()],
        cwd=repo, capture_output=True).returncode == 0
    report = cutover.check(repo, projection_dir=elsewhere)
    criterion = [c for c in report.criteria if c.name == "projection-is-shared-state"][0]

    print(f"  canonical projection files : {len(result.files)}")
    print(f"  inside the repository?     : {elsewhere.is_relative_to(repo)}")
    print(f"  committed at HEAD?         : {committed}")
    print(f"  criterion reports met?     : {criterion.met}")
    print(f'  its claim: "...over the projection at HEAD"')
    if criterion.met:
        print("  => a directory outside the repo, never committed, satisfies a criterion")
        print("     whose own text says HEAD. Fixing the DEFAULT path is not sufficient;")
        print("     --from must be constrained or removed.")


if __name__ == "__main__":
    main()
    from_flag_bypasses_head()
