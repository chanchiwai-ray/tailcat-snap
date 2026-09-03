#!/usr/bin/env bash
# Shared helpers for the tests/*.sh smoke-test scripts.
#
# These are integration/smoke tests against an already-installed
# `tailcat` snap (they do not build or install it -- see
# ../CONTRIBUTING.md). Each test_*.sh script should:
#   - source this file
#   - trap cleanup on EXIT
#   - use assert_* helpers, which print PASS/FAIL and track failures
#   - end with `exit_with_summary`
#
# Run a single script directly for its own summary, or use
# run_all.sh to run every test_*.sh and get an overall summary.

set -u
set -o pipefail

TESTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# tailcat's "home" plug only grants filesystem access under the real
# $HOME, excluding top-level dotfiles/dot-directories (see
# docs/known_issues.md #2/#4) -- so test workdirs must live directly
# under $HOME with a non-dot name, not under /tmp or a hidden
# directory, or tailcat-side file operations against them will fail
# for reasons unrelated to what's being tested.
WORKDIR="$(mktemp -d "$HOME/tailcat-test.XXXXXX")"
FAILURES=0
CHECKS=0

# Kill any tailcat/http.server processes left over from a previous
# run, best-effort.
cleanup() {
  pkill tailcat >/dev/null 2>&1 || true
  pkill -f "http.server" >/dev/null 2>&1 || true
  rm -rf "$WORKDIR"
}
trap cleanup EXIT

pass() {
  CHECKS=$((CHECKS + 1))
  echo "  PASS: $1"
}

fail() {
  CHECKS=$((CHECKS + 1))
  FAILURES=$((FAILURES + 1))
  echo "  FAIL: $1" >&2
}

# assert_contains <haystack-file-or-string> <needle> <description>
assert_contains() {
  local haystack="$1" needle="$2" desc="$3"
  if grep -qF -- "$needle" <<<"$haystack" 2>/dev/null || grep -qF -- "$needle" "$haystack" 2>/dev/null; then
    pass "$desc"
  else
    fail "$desc (expected to find: $needle)"
  fi
}

# assert_eq <actual> <expected> <description>
assert_eq() {
  local actual="$1" expected="$2" desc="$3"
  if [[ "$actual" == "$expected" ]]; then
    pass "$desc"
  else
    fail "$desc (expected [$expected], got [$actual])"
  fi
}

# assert_exit_code <actual-exit-code> <expected-exit-code> <description>
assert_exit_code() {
  local actual="$1" expected="$2" desc="$3"
  if [[ "$actual" -eq "$expected" ]]; then
    pass "$desc"
  else
    fail "$desc (expected exit $expected, got $actual)"
  fi
}

# assert_file_exists <path> <description>
assert_file_exists() {
  if [[ -f "$1" ]]; then
    pass "$2"
  else
    fail "$2 (file not found: $1)"
  fi
}

# extract_addr <logfile> -- prints the first tco... address found.
extract_addr() {
  grep -o 'tco[A-Za-z0-9_-]*' "$1" | head -1
}

# wait_for_addr <logfile> <max-seconds> -- polls until a tco... address
# appears in the file, or times out. Prints the address, or nothing.
wait_for_addr() {
  local logfile="$1" maxsec="${2:-10}" i=0
  while (( i < maxsec * 2 )); do
    local addr
    addr="$(extract_addr "$logfile" 2>/dev/null || true)"
    if [[ -n "$addr" ]]; then
      echo "$addr"
      return 0
    fi
    sleep 0.5
    i=$((i + 1))
  done
  return 1
}

# wait_for_pattern <logfile> <grep-pattern> <max-seconds> -- polls
# until a line matching the extended-regex pattern appears in the
# file, or times out. Prints the first matching line, or nothing.
wait_for_pattern() {
  local logfile="$1" pattern="$2" maxsec="${3:-10}" i=0
  while (( i < maxsec * 2 )); do
    local line
    line="$(grep -oP -- "$pattern" "$logfile" 2>/dev/null | head -1 || true)"
    if [[ -n "$line" ]]; then
      echo "$line"
      return 0
    fi
    sleep 0.5
    i=$((i + 1))
  done
  return 1
}

exit_with_summary() {
  echo
  if [[ "$FAILURES" -eq 0 ]]; then
    echo "=== $(basename "$0"): $CHECKS/$CHECKS checks passed ==="
    exit 0
  else
    echo "=== $(basename "$0"): $FAILURES/$CHECKS checks FAILED ===" >&2
    exit 1
  fi
}

require_tailcat() {
  if ! command -v tailcat >/dev/null 2>&1; then
    echo "tailcat is not installed or not on PATH -- install the snap first (see CONTRIBUTING.md)" >&2
    exit 1
  fi
}
