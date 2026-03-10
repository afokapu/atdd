#!/usr/bin/env bash
# Create all ATDD-vs-code-review gap issues on GitHub
# Usage: cd issues && bash create-all.sh
# Requires: gh auth login

set -euo pipefail

LABELS="atdd-issue,atdd:INIT"

declare -A TITLES=(
  ["01-security-pattern-validator"]="feat(atdd): Security pattern validator for coder phase"
  ["02-n-plus-one-query-detector"]="feat(atdd): N+1 query detection validator"
  ["03-dead-code-validator"]="feat(atdd): Dead code detection via AST reachability analysis"
  ["04-duplication-detector"]="feat(atdd): Intra-layer code duplication detector"
  ["05-error-message-quality-convention"]="feat(atdd): Error response contract and compliance validator"
  ["06-structured-logging-convention"]="feat(atdd): Structured logging convention and validator"
)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

for slug in 01-security-pattern-validator 02-n-plus-one-query-detector 03-dead-code-validator 04-duplication-detector 05-error-message-quality-convention 06-structured-logging-convention; do
  title="${TITLES[$slug]}"
  body_file="${SCRIPT_DIR}/${slug}.md"

  echo "Creating: ${title}"
  gh issue create \
    --title "${title}" \
    --body-file "${body_file}" \
    --label "${LABELS}" \
    || echo "FAILED: ${slug}"
  echo "---"
done

echo "Done. Run 'gh issue list' to verify."
