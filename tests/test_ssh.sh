#!/usr/bin/env bash
# tailcat ssh: remote command execution, landing in the server's real
# $HOME, and the coreutils-allowlist caveat (see known_issues.md #3).
set -u
cd "$(dirname "${BASH_SOURCE[0]}")"
source ./lib.sh
require_tailcat

timeout 20 tailcat serve no-auth-ssh > "$WORKDIR/ssh_server.log" 2>&1 &
disown
addr="$(wait_for_addr "$WORKDIR/ssh_server.log" 10)"
if [[ -z "$addr" ]]; then
  fail "ssh setup: server never printed an address"
else
  out="$(timeout 15 tailcat ssh "$addr" 'pwd' 2>&1)"
  assert_eq "$out" "$HOME" "ssh remote command runs in the server's real \$HOME"

  out="$(timeout 15 tailcat ssh "$addr" 'echo remote-exec-ok' 2>&1)"
  assert_contains "$out" "remote-exec-ok" "ssh runs an arbitrary remote command and returns its output"

  # Known caveat: only an allowlisted set of coreutils is exec-able
  # inside the confined server's shell session (see
  # docs/known_issues.md #3). whoami is a real-world example that's
  # NOT on the allowlist.
  out="$(timeout 15 tailcat ssh "$addr" whoami 2>&1)"
  if grep -qi "permission denied" <<<"$out"; then
    pass "ssh: whoami is denied by the strict-confinement coreutils allowlist, as documented"
  else
    fail "ssh: whoami unexpectedly succeeded -- has the confinement template's allowlist changed? Update known_issues.md #3 and this test if so. Got: $out"
  fi
fi
pkill tailcat >/dev/null 2>&1 || true

exit_with_summary
