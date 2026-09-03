#!/usr/bin/env bash
# --allow (client allowlisting) and --full-address.
set -u
cd "$(dirname "${BASH_SOURCE[0]}")"
source ./lib.sh
require_tailcat

CLIENT_KEY=tc_test_allow_client

cleanup_key() {
  tailcat genkey --delete --key="$CLIENT_KEY" >/dev/null 2>&1 || true
}

client_pub="$(tailcat genkey --client --key="$CLIENT_KEY" --force 2>&1 | tail -1)"
if [[ "$client_pub" != nodekey:* ]]; then
  fail "--allow setup: couldn't generate a client key"
else
  timeout 20 tailcat serve --allow="$client_pub" > "$WORKDIR/allow_server.log" 2>&1 &
  disown
  addr="$(wait_for_addr "$WORKDIR/allow_server.log" 10)"
  if [[ -z "$addr" ]]; then
    fail "--allow setup: server never printed an address"
  else
    msg="allowed client $(date +%s)"
    echo "$msg" | timeout 15 tailcat --key="$CLIENT_KEY" "$addr" >/dev/null 2>&1
    rc=$?
    assert_exit_code "$rc" 0 "--allow: the allowed client's connection succeeds"
    sleep 1
    assert_contains "$WORKDIR/allow_server.log" "$msg" "--allow: the allowed client's message reached the server"
  fi
  pkill tailcat >/dev/null 2>&1 || true
  sleep 1

  # A different (unlisted, ephemeral) client key should be rejected.
  timeout 20 tailcat serve --allow="$client_pub" > "$WORKDIR/allow_server2.log" 2>&1 &
  disown
  addr2="$(wait_for_addr "$WORKDIR/allow_server2.log" 10)"
  if [[ -z "$addr2" ]]; then
    fail "--allow disallowed-client setup: server never printed an address"
  else
    echo "disallowed client" | timeout 8 tailcat --key=new "$addr2" >/dev/null 2>&1
    rc=$?
    if [[ "$rc" -ne 0 ]]; then
      pass "--allow: an unlisted client's connection is rejected (times out / fails)"
    else
      fail "--allow: an unlisted client was unexpectedly allowed through"
    fi
  fi
  pkill tailcat >/dev/null 2>&1 || true
fi
cleanup_key
sleep 1

# --- --full-address ---
timeout 15 tailcat > "$WORKDIR/short_server.log" 2>&1 &
disown
short_addr="$(wait_for_addr "$WORKDIR/short_server.log" 10)"
pkill tailcat >/dev/null 2>&1 || true
sleep 1

timeout 15 tailcat serve --full-address > "$WORKDIR/fa_server.log" 2>&1 &
disown
full_addr="$(wait_for_addr "$WORKDIR/fa_server.log" 10)"
if [[ -z "$full_addr" || -z "$short_addr" ]]; then
  fail "--full-address: setup: a server never printed an address"
elif [[ "${#full_addr}" -gt "${#short_addr}" ]]; then
  pass "--full-address: printed address is longer than a plain short address (embeds DERP info)"
else
  fail "--full-address: printed address (${#full_addr} chars) is not longer than a short address (${#short_addr} chars)"
fi
pkill tailcat >/dev/null 2>&1 || true

exit_with_summary
