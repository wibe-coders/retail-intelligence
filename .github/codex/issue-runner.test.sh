#!/usr/bin/env bash

set -euo pipefail

readonly TEST_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
source "$TEST_ROOT/.github/codex/issue-runner.sh"

test_branch_name_uses_numeric_issue() {
  ISSUE_NUMBER=42
  [[ $(branch_name) == 'codex/issue-42' ]]
}

test_context_rejects_non_numeric_issue() {
  GITHUB_WORKSPACE=$TEST_ROOT
  RUNNER_TEMP=${TMPDIR:-/tmp}
  ISSUE_NUMBER='../main'
  REPOSITORY='wibe-coders/retail-intelligence'
  ! require_context >/dev/null 2>&1
}

test_state_round_trip() {
  local test_temp
  test_temp=$(mktemp -d)
  RUNNER_TEMP=$test_temp
  write_state partial 'test blocker'
  [[ $(jq -r '.status' "$(state_file)") == partial ]]
  [[ $(jq -r '.detail' "$(state_file)") == 'test blocker' ]]
  rm -r "$test_temp"
}

test_result_schema_is_valid_json() {
  jq -e '.required == ["status", "summary", "tests", "blocker"]' \
    "$TEST_ROOT/.github/codex/result.schema.json" >/dev/null
}

test_branch_name_uses_numeric_issue
test_context_rejects_non_numeric_issue
test_state_round_trip
test_result_schema_is_valid_json
printf '%s\n' 'issue-runner tests passed'

