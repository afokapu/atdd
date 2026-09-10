#!/usr/bin/env bash
# SPIKE: what can a pre-push hook do about a file it resyncs?
# Subject under test: git <-> pre-push hook <-> remote. ATDD is stubbed.
set -u
ROOT="$(cd "$(dirname "$0")" && pwd)"

setup() {                       # $1 = variant name, $2 = hook body
  rm -rf "$ROOT/$1"; mkdir -p "$ROOT/$1"; cd "$ROOT/$1" || exit 1
  git init -q --bare origin.git
  git init -q work && cd work
  git config user.email l@b; git config user.name lab
  git remote add origin ../origin.git
  echo "total: 11" > mirror.yaml; echo "src v1" > source.yaml
  git add -A; git commit -qm "base"; git push -q origin HEAD:main

  mkdir -p .githooks
  cat > .githooks/pre-push <<HOOK
#!/usr/bin/env bash
# stub of 'atdd registry update --check': always reports drift
echo "LAB: drift detected" >&2
# stub of 'atdd registry update --yes': rewrites the mirror
echo "total: 12" > mirror.yaml
$2
HOOK
  chmod +x .githooks/pre-push
  git config core.hooksPath .githooks
}

report() {                      # $1 = variant name
  cd "$ROOT/$1/work" || return
  echo "  push exit code : $PUSH_RC"
  echo "  local HEAD     : $(git rev-parse --short HEAD)"
  echo "  remote main    : $(git --git-dir=../origin.git rev-parse --short main 2>/dev/null || echo NONE)"
  echo "  mirror ON REMOTE: $(git --git-dir=../origin.git show main:mirror.yaml 2>/dev/null | tr -d '\n' || echo MISSING)"
  echo "  mirror in HEAD  : $(git show HEAD:mirror.yaml | tr -d '\n')"
  echo "  worktree status : $(git status --short | tr '\n' ' ' | sed 's/ *$//' || echo clean)"
}

run() {                         # $1 = name, $2 = hook body, $3 = description
  echo "=============================================================="
  echo "VARIANT $1 — $3"
  echo "=============================================================="
  setup "$1" "$2"
  echo "v2" >> source.yaml; git add source.yaml; git commit -qm "change source"
  git push origin HEAD:main >/dev/null 2>&1; PUSH_RC=$?
  report "$1"
  echo
}

run A 'git add mirror.yaml' \
    "CURRENT SHIPPED BEHAVIOUR: git add, no commit, hook returns 0"

run B 'git add mirror.yaml
git commit --amend --no-edit -q' \
    "AMEND: stage + amend HEAD during pre-push"

run C 'git add mirror.yaml
echo "ATDD: mirror drift resynced and staged. Commit it, then push again." >&2
exit 1' \
    "BLOCK: stage the fix, refuse the push, tell the operator"
