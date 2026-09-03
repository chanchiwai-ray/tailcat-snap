#!/usr/bin/env bash
# genkey: basic generation, --list, --delete, --client, --region=list,
# --region=<code>, --fixed-region, and the --embed-derp-map crash
# (see docs/known_issues.md #5) plus its workaround.
set -u
cd "$(dirname "${BASH_SOURCE[0]}")"
source ./lib.sh
require_tailcat

KEYS=(tc_test_basic tc_test_client tc_test_region tc_test_fixed tc_test_embed_ok)

cleanup_keys() {
  for k in "${KEYS[@]}" tc_test_embed_bug; do
    tailcat genkey --delete --key="$k" >/dev/null 2>&1 || true
  done
}

# --- basic genkey + list + delete ---
out="$(tailcat genkey --key=tc_test_basic --force 2>&1)"
assert_contains "$out" "tco" "genkey generates and prints a tco... address"

out="$(tailcat genkey --list 2>&1)"
assert_contains "$out" "tc_test_basic" "genkey --list shows the newly created key"

tailcat genkey --delete --key=tc_test_basic >/dev/null 2>&1
out="$(tailcat genkey --list 2>&1)"
if grep -qF "tc_test_basic" <<<"$out"; then
  fail "genkey --delete removes the key from --list"
else
  pass "genkey --delete removes the key from --list"
fi

# --- --client ---
out="$(tailcat genkey --client --key=tc_test_client --force 2>&1)"
assert_contains "$out" "nodekey:" "genkey --client prints a nodekey: public key"

# --- --region=list ---
out="$(timeout 15 tailcat genkey --region=list 2>&1)"
assert_contains "$out" "fra" "genkey --region=list includes the Frankfurt region"

# --- --region=<code> ---
out="$(timeout 15 tailcat genkey --key=tc_test_region --region=fra --force 2>&1)"
assert_contains "$out" "tco" "genkey --region=fra generates a key/address"

# --- --fixed-region ---
out="$(timeout 15 tailcat genkey --key=tc_test_fixed --fixed-region --force 2>&1)"
assert_contains "$out" "tco" "genkey --fixed-region generates a key/address"

# --- --embed-derp-map with explicit --region (the documented workaround; should succeed) ---
out="$(timeout 15 tailcat genkey --key=tc_test_embed_ok --embed-derp-map --region=fra --force 2>&1)"
assert_contains "$out" "tco" "genkey --embed-derp-map with an explicit --region succeeds"

# --- --embed-derp-map with the DEFAULT --region=auto (known upstream bug, see known_issues.md #5) ---
out="$(timeout 15 tailcat genkey --key=tc_test_embed_bug --embed-derp-map --force 2>&1)"
rc=$?
if [[ "$rc" -ne 0 ]]; then
  pass "genkey --embed-derp-map --region=auto (default) fails as documented (known upstream bug, see known_issues.md #5)"
else
  fail "genkey --embed-derp-map --region=auto (default) unexpectedly succeeded -- has the upstream bug been fixed? Update known_issues.md #5 and this test if so."
fi
tailcat genkey --delete --key=tc_test_embed_bug >/dev/null 2>&1 || true

cleanup_keys
exit_with_summary
