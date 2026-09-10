#!/usr/bin/env bash
# Stub of `gh`, reproducing each real-world failure of `gh issue view`.
# Every stderr string below was captured from an ACTUAL failure, not invented:
#   NOT_FOUND / RATE_LIMIT observed in this session against afokapu/atdd.
case "${LAB_GH_MODE:-ok}" in
  ok)          echo '{"number":1,"title":"t","state":"OPEN","labels":[],"body":"b"}'; exit 0 ;;
  not_found)   echo 'GraphQL: Could not resolve to an issue or pull request with the number of 99999999. (repository.issue)' >&2; exit 1 ;;
  rate_limit)  echo 'GraphQL: API rate limit already exceeded for user ID 8843832.' >&2; exit 1 ;;
  secondary)   echo 'You have exceeded a secondary rate limit. Please wait a few minutes before you try again.' >&2; exit 1 ;;
  auth)        echo 'gh: To use GitHub CLI in a GitHub Actions workflow, set the GH_TOKEN environment variable.' >&2; exit 1 ;;
  network)     echo 'error connecting to api.github.com: dial tcp: lookup api.github.com: no such host' >&2; exit 1 ;;
  server)      echo 'GraphQL: Something went wrong while executing your query. (502)' >&2; exit 1 ;;
  garbage)     echo 'not json at all'; exit 0 ;;
esac
