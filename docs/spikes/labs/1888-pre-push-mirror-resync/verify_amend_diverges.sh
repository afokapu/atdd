#!/usr/bin/env bash
set -u
ROOT="$(cd "$(dirname "$0")" && pwd)"; rm -rf "$ROOT/B2"; mkdir -p "$ROOT/B2"; cd "$ROOT/B2"
git init -q --bare origin.git; git init -q work; cd work
git config user.email l@b; git config user.name lab; git remote add origin ../origin.git
echo "total: 11" > mirror.yaml; echo "src v1" > source.yaml
git add -A; git commit -qm base; git push -q origin HEAD:main
mkdir -p .githooks
cat > .githooks/pre-push <<'HOOK'
#!/usr/bin/env bash
echo "LAB-HOOK: sha at hook entry = $(git rev-parse --short HEAD)" >&2
echo "LAB-HOOK: refs git handed me on stdin:" >&2
while read -r line; do echo "LAB-HOOK:   $line" >&2; done
echo "total: 12" > mirror.yaml
git add mirror.yaml
git commit --amend --no-edit -q
echo "LAB-HOOK: sha after amend    = $(git rev-parse --short HEAD)" >&2
HOOK
chmod +x .githooks/pre-push; git config core.hooksPath .githooks
echo "v2" >> source.yaml; git add source.yaml; git commit -qm "change source"
PRE=$(git rev-parse HEAD); echo ">>> sha BEFORE push: $(git rev-parse --short HEAD)"
git push origin HEAD:main 2>&1 | sed 's/^/    /'
echo ">>> push exit: ${PIPESTATUS[0]}"
POST=$(git rev-parse HEAD); REMOTE=$(git --git-dir=../origin.git rev-parse main)
echo ">>> local HEAD after : $(git rev-parse --short HEAD)"
echo ">>> remote main      : $(git --git-dir=../origin.git rev-parse --short main)"
echo
[ "$REMOTE" = "$PRE" ] && echo "VERDICT: remote received the PRE-AMEND commit" \
                       || { [ "$REMOTE" = "$POST" ] && echo "VERDICT: remote received the amended commit" \
                       || echo "VERDICT: remote matches NEITHER"; }
[ "$REMOTE" = "$POST" ] || echo "VERDICT: local HEAD and remote have DIVERGED after an exit-0 push"
echo ">>> mirror content on remote: $(git --git-dir=../origin.git show main:mirror.yaml | tr -d '\n')"
echo ">>> worktree after push     : $(git status --short | grep -v githooks | tr '\n' ' ')[clean if empty]"
