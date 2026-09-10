#!/usr/bin/env bash
set -u
ROOT="$(cd "$(dirname "$0")" && pwd)"; rm -rf "$ROOT/D"; mkdir -p "$ROOT/D"; cd "$ROOT/D"
git init -q --bare origin.git; git init -q work; cd work
git config user.email l@b; git config user.name lab; git remote add origin ../origin.git
echo "total: 11" > mirror.yaml; echo "src v1" > source.yaml
git add -A; git commit -qm base; git push -q origin HEAD:main
mkdir -p .githooks; git config core.hooksPath .githooks
# HEAL AT PRE-COMMIT: does `git add` here reach the commit being created?
cat > .githooks/pre-commit <<'HOOK'
#!/usr/bin/env bash
echo "LAB-HOOK(pre-commit): drift detected; resyncing mirror" >&2
echo "total: 12" > mirror.yaml
git add mirror.yaml
HOOK
# pre-push stays as a truthful gate: refuse if drift is STILL present
cat > .githooks/pre-push <<'HOOK'
#!/usr/bin/env bash
if ! grep -q "total: 12" "$(git rev-parse --show-toplevel)/mirror.yaml"; then
  echo "LAB-HOOK(pre-push): mirror still drifted — refusing push" >&2; exit 1
fi
echo "LAB-HOOK(pre-push): mirror in sync; allowing push" >&2
HOOK
chmod +x .githooks/pre-commit .githooks/pre-push
echo "v2" >> source.yaml; git add source.yaml
git commit -qm "change source" 2>&1 | sed 's/^/    /'
echo ">>> mirror inside the new commit : $(git show HEAD:mirror.yaml | tr -d '\n')"
git push origin HEAD:main 2>&1 | sed 's/^/    /'; RC=${PIPESTATUS[0]}
echo ">>> push exit                    : $RC"
echo ">>> local HEAD                   : $(git rev-parse --short HEAD)"
echo ">>> remote main                  : $(git --git-dir=../origin.git rev-parse --short main)"
echo ">>> mirror ON REMOTE             : $(git --git-dir=../origin.git show main:mirror.yaml | tr -d '\n')"
echo ">>> worktree after               : $(git status --short | grep -v githooks | tr '\n' ' ')[clean if empty]"
