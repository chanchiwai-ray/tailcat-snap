#!/usr/bin/env bash
# Runs every tests/test_*.sh smoke-test script against an
# already-installed tailcat snap and prints an overall summary.
#
# Usage: tests/run_all.sh
#
# See ../CONTRIBUTING.md for prerequisites (tailcat must already be
# installed).
set -u
cd "$(dirname "${BASH_SOURCE[0]}")"

if ! command -v tailcat >/dev/null 2>&1; then
  echo "tailcat is not installed or not on PATH -- install the snap first (see ../CONTRIBUTING.md)" >&2
  exit 1
fi

total_pass=0
total_fail=0
failed_scripts=()

for script in test_*.sh; do
  echo "##############################################"
  echo "# $script"
  echo "##############################################"
  if bash "$script"; then
    total_pass=$((total_pass + 1))
  else
    total_fail=$((total_fail + 1))
    failed_scripts+=("$script")
  fi
  echo
done

echo "=============================================="
echo "Ran $((total_pass + total_fail)) test scripts: $total_pass passed, $total_fail failed"
if [[ "$total_fail" -gt 0 ]]; then
  echo "Failed scripts:"
  for s in "${failed_scripts[@]}"; do
    echo "  - $s"
  done
  exit 1
fi
exit 0
