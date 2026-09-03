#!/usr/bin/env bash
# Documents/verifies two confinement-caused failure modes rather than
# successes, matching docs/known_issues.md:
#   - cp's local-side path must be under $HOME (issue #3's note)
#   - socks <addr> <cmd> can't exec external tools like curl (issue #6)
set -u
cd "$(dirname "${BASH_SOURCE[0]}")"
source ./lib.sh
require_tailcat

# --- cp: local path outside $HOME fails ---
mkdir -p "$WORKDIR/files_rw2"
timeout 20 tailcat serve --files="$WORKDIR/files_rw2:rw" files > "$WORKDIR/cp_server.log" 2>&1 &
disown
addr="$(wait_for_addr "$WORKDIR/cp_server.log" 10)"
if [[ -z "$addr" ]]; then
  fail "cp-outside-home setup: server never printed an address"
else
  echo "should fail" > /tmp/tailcat_outside_home_test.txt
  timeout 15 tailcat cp /tmp/tailcat_outside_home_test.txt "$addr:" >/dev/null 2>&1
  rc=$?
  if [[ "$rc" -ne 0 ]]; then
    pass "cp: a local path under /tmp (outside \$HOME) is correctly rejected, as documented"
  else
    fail "cp: a local path under /tmp unexpectedly succeeded -- has the home-plug restriction changed? Update known_issues.md and this test if so."
  fi
  rm -f /tmp/tailcat_outside_home_test.txt
fi
pkill tailcat >/dev/null 2>&1 || true
sleep 1

# --- socks <cmd>: curl isn't visible inside the snap's confined view ---
timeout 20 tailcat serve 18099 > "$WORKDIR/socks_cmd_server.log" 2>&1 &
disown
addr2="$(wait_for_addr "$WORKDIR/socks_cmd_server.log" 10)"
if [[ -z "$addr2" ]]; then
  fail "socks <cmd> setup: server never printed an address"
else
  out="$(timeout 15 tailcat socks "$addr2" curl -s http://server.tailcat:18099/ 2>&1)"
  if grep -qi "executable file not found" <<<"$out"; then
    pass "socks <cmd> curl: fails with 'executable file not found', as documented (known_issues.md #6)"
  else
    fail "socks <cmd> curl: unexpected result -- has curl been bundled or become visible? Update known_issues.md #6 and this test if so. Got: $out"
  fi
fi
pkill tailcat >/dev/null 2>&1 || true

exit_with_summary
