#!/usr/bin/env bash
# SPIKE (#4 / train identity): what does the WRITE path accept today, and what
# would validating it cost?
#
# Subject under test: the real `atdd` CLI's train write path against a real
# project with a real _trains.yaml. Nothing is stubbed — the question is about
# the shipped CLI's behaviour, so a stub would answer a different question.
set -u
ROOT="$(cd "$(dirname "$0")" && pwd)"
PROJ="$ROOT/proj"
rm -rf "$PROJ"; mkdir -p "$PROJ/plan/_trains"

cat > "$PROJ/plan/_trains.yaml" <<'YAML'
trains:
  demo-theme:
    nominal:
      - train_id: "train:demo:canonical-one"
        description: "A canonical typed train."
        path: plan/_trains/canonical-one.yaml
        wagons: [demo-wagon]
      - train_id: "0009-legacy-one"
        description: "A legacy numbered train, still registered."
        path: plan/_trains/0009-legacy-one.yaml
        wagons: [demo-wagon]
YAML
printf 'train_id: "train:demo:canonical-one"\n' > "$PROJ/plan/_trains/canonical-one.yaml"
printf 'train_id: "0009-legacy-one"\n'          > "$PROJ/plan/_trains/0009-legacy-one.yaml"

cd "$PROJ" || exit 1
git init -q -b main .; git config user.email l@b; git config user.name lab
git add -A >/dev/null 2>&1; git commit -qm base >/dev/null 2>&1

printf '%-34s %-9s %s\n' "VALUE PASSED TO --train" "ACCEPTED" "CLASS"
printf '%-34s %-9s %s\n' "----------------------" "--------" "-----"
probe() {                       # $1 = value, $2 = what it is
  out=$(atdd update 9999 --train "$1" 2>&1); rc=$?
  if [ $rc -eq 0 ] && printf '%s' "$out" | grep -q "train: $1"; then a="yes"; else a="no"; fi
  printf '%-34s %-9s %s\n' "$1" "$a" "$2"
}
probe "train:demo:canonical-one"  "canonical, registered"
probe "0009-legacy-one"           "legacy, registered"
probe "train:0009-legacy-one"     "legacy w/ prefix, registered"
probe "train:demo:not-registered" "canonical SHAPE, unregistered"
probe "0003-author-substrate"     "legacy shape, DANGLING in the real repo"
probe "INVALID"                   "not a train identity at all"
probe "train:"                    "empty after prefix"
probe ""                          "empty string"
