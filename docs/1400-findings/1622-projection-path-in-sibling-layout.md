# #1622 — `atdd state project` writes where git cannot see it, in this repo's own layout

Found 2026-09-13 while staging the cutover. Not a disposition question, and not fixed here.

## The divergence

This Control Root is `sibling-worktree`: `/Users/alecfokapu/Github/atdd` holds `.atdd/`, and
the 114 git worktrees are siblings beneath it. The container is **not a git repository**.

Three parts of the system resolve the projection directory, and two of them disagree:

| | resolves to | from |
|---|---|---|
| `atdd state project` (default `--out`) | `<control-root>/.atdd/state/projection` | `projection_cli.py:68` |
| `atdd state cutover` (default `--root`) | `<cwd>/.atdd/state/projection` | `migrate_cli.py:130` — `args.root or Path.cwd()` |
| `merge_authority`, `gitstore.projection_at` | `<repo>/.atdd/state/projection` | `merge_authority.py:298`, `gitstore.py:70` |

Under `single-repo` all three are one directory and nothing shows. Under `sibling-worktree`
the first is outside git entirely, so:

- `atdd state project` writes a projection **no commit can contain**, which defeats
  "first *committed* projection" (C002) and `atdd state cutover`'s
  `projection-is-shared-state`.
- Run back to back from a worktree, `project` then `cutover` report **unmet** — they are
  looking at different directories.
- `git ls-tree <commit>:.atdd/state/projection` in `gitstore.projection_at` can never find
  it, so the merge driver has nothing to judge.

Measured, not inferred:

    layout: sibling-worktree
    project writes : /Users/alecfokapu/Github/atdd/.atdd/state/projection
    cutover reads  : /Users/alecfokapu/Github/atdd/worktrees/feat-…/.atdd/state/projection
    project-out == cutover-in ?  False
    control root is a git repo ? False

## Why it matters beyond #1622

The projection is shared state. Its whole purpose is to be committed and merged between
peers; a directory outside the repository is a local artifact that no peer will ever see.
The default is therefore wrong in a way that is silent — it writes successfully, exits zero,
and produces something structurally incapable of being what it is for.

## Working around it for the cutover

Pass the destination explicitly and run the check from the same place:

    atdd state project --out <worktree>/.atdd/state/projection
    git add .atdd/state/projection && git commit
    atdd state cutover            # from <worktree>, so --root resolves there

That is a workaround, not the fix. The fix is a ruling on where the projection belongs when
the Control Root and the git worktree are different directories — most likely "always the
git worktree root", since every git-facing consumer already assumes that.

## Status

Not blocking the dispositions, which are landed and proven. It blocks the *cutover step*,
and it wants its own issue rather than riding in on #1622 — the same call taken for #2006.
