"""#2042 lab, probe 2 — does a truncated projection survive every check?

The issue's claim: byte-identity, self-canonicality and the cutover's exit
criterion all compare the projection to itself or to a projection of the same
snapshot, so a projection missing objects the store holds passes all of them.

This builds a REAL git repo with a REAL store, commits a projection, then deletes
one document from it and commits again. Then it asks each check, in turn, what it
thinks — reading out of git, exactly as the blocking gate does.

The bar #2042 sets is one line: a projection with an object deliberately removed
must fail. Any check that still reports MET here is not a coverage check.

**VERDICT FLIPPED (coverage has landed).** This ran first as a demonstration that
the truncation survived every check; it now runs as the REGRESSION CHECK that it
does not. It exits zero when the truncation is REFUSED and non-zero if the old
behaviour ever comes back — so the file that proved the defect is the file that
keeps it dead, and the sign of its verdict is the whole record of what changed.

Usage:  python truncation.py
"""
from __future__ import annotations

import pathlib
import subprocess
import sys
import tempfile

from atdd.state import cutover, gitstore
from atdd.state import projection as P
from atdd.state.store import StateStore

_SEED = (("alpha-item", "PLANNED"), ("beta-item", "RED"), ("gamma-item", "GREEN"))


def _git(repo: pathlib.Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=str(repo), capture_output=True, text=True)


def _new_repo(path: pathlib.Path) -> pathlib.Path:
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "--quiet", "-b", "main")
    _git(path, "config", "user.email", "lab@atdd.test")
    _git(path, "config", "user.name", "Coverage Lab")
    (path / ".atdd" / "state").mkdir(parents=True, exist_ok=True)
    (path / ".gitignore").write_text(".atdd/state/state.sqlite*\n", encoding="utf-8")
    return path


def _seed_store(root: pathlib.Path) -> list[str]:
    from atdd.state.db import connect, init_state_store
    from atdd.state.work_item_writer import create_work_item

    conn = connect(init_state_store(start=root))
    try:
        return [
            create_work_item(conn, slug, state=phase, data={"title": slug}).uid
            for slug, phase in _SEED
        ]
    finally:
        conn.close()


def _commit_projection(root: pathlib.Path, message: str) -> None:
    _git(root, "add", "-A")
    _git(root, "commit", "--quiet", "-m", message)


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = _new_repo(pathlib.Path(tmp) / "repo")
        uids = _seed_store(root)
        out = root / P.PROJECTION_RELATIVE

        from atdd.state.db import connect, init_state_store
        conn = connect(init_state_store(start=root))
        try:
            P.project(StateStore(conn), out)
        finally:
            conn.close()
        _commit_projection(root, "the whole projection")

        committed = gitstore.projection_bytes_at(root, "HEAD", P.PROJECTION_RELATIVE.as_posix())
        print(f"seeded store work items : {len(uids)}")
        print(f"committed documents     : {len(committed)}")
        full = cutover.check(root, projection_dir=out)
        print(f"cutover projection criterion, WHOLE projection : "
              f"{'MET' if full.criteria[0].met else 'UNMET'}")

        # --- now remove one object and commit the truncation -----------------
        victim = sorted(committed)[0]
        (out / victim).unlink()
        _commit_projection(root, "truncated: one document removed")

        after = gitstore.projection_bytes_at(root, "HEAD", P.PROJECTION_RELATIVE.as_posix())
        print(f"\nremoved {victim}")
        print(f"committed documents now : {len(after)}   (store still holds {len(uids)})")

        truncated = cutover.check(root, projection_dir=out)
        criterion = truncated.criteria[0]
        print(f"cutover projection criterion, TRUNCATED        : "
              f"{'MET' if criterion.met else 'UNMET'}")

        # byte-identity and self-canonicality, asked directly
        report = P.check_canonicality(out)
        print(f"check_canonicality over the truncated tree     : "
              f"{'canonical' if report.ok else 'NOT canonical'}")
        print(f"non-empty                                      : {len(after) > 0}")

        print("\n" + "=" * 62)
        if not criterion.met:
            print("REGRESSION CHECK PASSES — the truncation is REFUSED.")
            print("The criterion names what is gone:")
            for blocker in criterion.blockers:
                print(f"    {blocker}")
            print()
            print("Note what did NOT change: byte-identity and self-canonicality still")
            print(f"report the tree canonical ({'canonical' if report.ok else 'NOT canonical'}),")
            print("and non-empty is still True. They were never wrong — they answer a")
            print("different question. Coverage is the one that consults the store.")
            return 0
        print("REGRESSION — the cutover certified a projection missing an object the")
        print("store holds. This is the #2042 defect returning: every check in the")
        print("chain is comparing the projection to itself again.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
