#!/usr/bin/env bash
# Basic invocation subcommands that need no server: --help, version,
# printpub, parse, resolve, readme.
set -u
cd "$(dirname "${BASH_SOURCE[0]}")"
source ./lib.sh
require_tailcat

out="$(tailcat --help 2>&1)"
assert_contains "$out" "SUBCOMMANDS" "--help prints usage with a SUBCOMMANDS section"

out="$(tailcat --version 2>&1)"
assert_contains "$out" "." "--version prints a version string"

out="$(tailcat version 2>&1)"
assert_contains "$out" "." "version subcommand prints a version string"

out="$(tailcat printpub 2>&1)"
assert_contains "$out" "nodekey:" "printpub prints a nodekey: public key"

out="$(tailcat readme 2>&1)"
assert_contains "$out" "Tailcat" "readme prints the upstream README"

# parse: needs an address. Generate one via a short-lived server.
timeout 15 tailcat > "$WORKDIR/server.log" 2>&1 &
disown
addr="$(wait_for_addr "$WORKDIR/server.log" 10)"
if [[ -z "$addr" ]]; then
  fail "parse/resolve setup: server never printed an address"
else
  out="$(tailcat parse "$addr" 2>&1)"
  assert_contains "$out" "ServerPublic" "parse prints JSON with ServerPublic"
  assert_contains "$out" "RegionID" "parse prints JSON with RegionID"

  out="$(timeout 15 tailcat resolve "$addr" 2>&1)"
  assert_contains "$out" "tco" "resolve prints an expanded tco... address"
  # The resolved address should be longer (embeds DERP node info).
  if [[ "${#out}" -gt "${#addr}" ]]; then
    pass "resolved address is longer than the input (embeds DERP info)"
  else
    fail "resolved address is not longer than the input"
  fi
fi
pkill tailcat >/dev/null 2>&1 || true

exit_with_summary
