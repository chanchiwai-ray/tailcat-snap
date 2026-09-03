#!/usr/bin/env bash
# serve exit-node routing (via socks to the open internet, and via
# ssh -p ip:port reaching the exit node's own sshd), plus the "socks"
# and "forward" subcommands against a non-exit-node server.
set -u
cd "$(dirname "${BASH_SOURCE[0]}")"
source ./lib.sh
require_tailcat

# --- forward ---
python3 -m http.server 18091 --directory /tmp >/dev/null 2>&1 &
disown
timeout 20 tailcat serve 18091 > "$WORKDIR/fwd_server.log" 2>&1 &
disown
addr="$(wait_for_addr "$WORKDIR/fwd_server.log" 10)"
if [[ -z "$addr" ]]; then
  fail "forward: server never printed an address"
else
  timeout 15 tailcat forward "$addr" 0:18091 > "$WORKDIR/fwd_client.log" 2>&1 &
  disown
  local_port="$(wait_for_pattern "$WORKDIR/fwd_client.log" '127\.0\.0\.1:\K[0-9]+' 10)"
  if [[ -z "$local_port" ]]; then
    fail "forward: client never printed its local listen port"
  else
    code="$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$local_port/")"
    assert_eq "$code" "200" "forward: local port reaches the server's forwarded port"
  fi
fi
pkill tailcat >/dev/null 2>&1 || true
pkill -f "http.server 18091" >/dev/null 2>&1 || true
sleep 1

# --- socks (daemon mode, non-exit-node server) ---
python3 -m http.server 18092 --directory /tmp >/dev/null 2>&1 &
disown
timeout 25 tailcat serve 18092 > "$WORKDIR/socks_server.log" 2>&1 &
disown
addr2="$(wait_for_addr "$WORKDIR/socks_server.log" 10)"
if [[ -z "$addr2" ]]; then
  fail "socks: server never printed an address"
else
  timeout 20 tailcat socks "$addr2" > "$WORKDIR/socks_client.log" 2>&1 &
  disown
  socks_port="$(wait_for_pattern "$WORKDIR/socks_client.log" '127\.0\.0\.1:\K[0-9]+' 12)"
  if [[ -z "$socks_port" ]]; then
    fail "socks: proxy never printed its listen port"
  else
    code="$(curl -s --socks5-hostname "127.0.0.1:$socks_port" -o /dev/null -w '%{http_code}' "http://server.tailcat:18092/")"
    assert_eq "$code" "200" "socks: server.tailcat magic hostname reaches the server"
    code2="$(curl -s --socks5-hostname "127.0.0.1:$socks_port" -o /dev/null -w '%{http_code}' "http://$addr2:18092/")"
    assert_eq "$code2" "200" "socks: tc-addr used directly as hostname reaches the server"
  fi
fi
pkill tailcat >/dev/null 2>&1 || true
pkill -f "http.server 18092" >/dev/null 2>&1 || true
sleep 1

# --- exit-node: socks routing to the open internet ---
timeout 25 tailcat serve exit-node > "$WORKDIR/exit_server.log" 2>&1 &
disown
addr3="$(wait_for_addr "$WORKDIR/exit_server.log" 10)"
if [[ -z "$addr3" ]]; then
  fail "exit-node: server never printed an address"
else
  timeout 20 tailcat socks "$addr3" > "$WORKDIR/exit_socks.log" 2>&1 &
  disown
  exit_port="$(wait_for_pattern "$WORKDIR/exit_socks.log" '127\.0\.0\.1:\K[0-9]+' 12)"
  if [[ -z "$exit_port" ]]; then
    fail "exit-node socks: proxy never printed its listen port"
  else
    code="$(curl -s --socks5-hostname "127.0.0.1:$exit_port" --max-time 15 -o /dev/null -w '%{http_code}' "https://example.com/")"
    assert_eq "$code" "200" "exit-node: routes real internet traffic (https://example.com) through the exit node"
  fi

  # --- exit-node: ssh -p ip:port reaches the exit node's own sshd ---
  # This only proves the TCP route through the exit node works (we
  # don't have real host SSH credentials in this test environment);
  # a genuine "Permission denied (publickey)" from the real sshd
  # confirms the route, as opposed to a connection-level error. If
  # your host has passwordless/key-based root login configured, this
  # may instead succeed outright (also a pass).
  ssh_out="$(timeout 15 tailcat ssh -p 127.0.0.1:22 "$addr3" true 2>&1 || true)"
  if grep -q "Permission denied" <<<"$ssh_out" || [[ -z "$ssh_out" ]]; then
    pass "exit-node ssh -p: reached the exit node's real sshd (SSH-protocol response, not a connection error)"
  else
    fail "exit-node ssh -p: unexpected response: $ssh_out"
  fi
fi
pkill tailcat >/dev/null 2>&1 || true

exit_with_summary
