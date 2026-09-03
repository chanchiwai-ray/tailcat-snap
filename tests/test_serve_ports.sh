#!/usr/bin/env bash
# serve <port>, serve all, and a combined serve <port>,no-auth-ssh.
set -u
cd "$(dirname "${BASH_SOURCE[0]}")"
source ./lib.sh
require_tailcat

http_body_ok() {
  # Reads an HTTP response piped over tailcat and checks for 200 OK.
  local addr="$1" port="$2"
  echo -e "GET / HTTP/1.0\r\nHost: local\r\n\r\n" | timeout 15 tailcat "$addr" "$port" 2>/dev/null | head -1
}

# --- serve <port> ---
python3 -m http.server 18080 --directory /tmp >/dev/null 2>&1 &
disown
timeout 20 tailcat serve 18080 > "$WORKDIR/serve1.log" 2>&1 &
disown
addr="$(wait_for_addr "$WORKDIR/serve1.log" 10)"
if [[ -z "$addr" ]]; then
  fail "serve <port>: server never printed an address"
else
  resp="$(http_body_ok "$addr" 18080)"
  assert_contains "$resp" "200 OK" "serve <port> forwards to the local HTTP server"
fi
pkill tailcat >/dev/null 2>&1 || true
pkill -f "http.server 18080" >/dev/null 2>&1 || true
sleep 1

# --- serve all ---
python3 -m http.server 18081 --directory /tmp >/dev/null 2>&1 &
disown
timeout 20 tailcat serve all > "$WORKDIR/serve2.log" 2>&1 &
disown
addr2="$(wait_for_addr "$WORKDIR/serve2.log" 10)"
if [[ -z "$addr2" ]]; then
  fail "serve all: server never printed an address"
else
  resp="$(http_body_ok "$addr2" 18081)"
  assert_contains "$resp" "200 OK" "serve all forwards to a port not explicitly named"
fi
pkill tailcat >/dev/null 2>&1 || true
pkill -f "http.server 18081" >/dev/null 2>&1 || true
sleep 1

# --- serve <port>,no-auth-ssh (combined services) ---
python3 -m http.server 18082 --directory /tmp >/dev/null 2>&1 &
disown
timeout 20 tailcat serve 18082,no-auth-ssh > "$WORKDIR/serve3.log" 2>&1 &
disown
addr3="$(wait_for_addr "$WORKDIR/serve3.log" 10)"
if [[ -z "$addr3" ]]; then
  fail "combined serve: server never printed an address"
else
  resp="$(http_body_ok "$addr3" 18082)"
  assert_contains "$resp" "200 OK" "combined serve: port forwarding still works"
  ssh_out="$(timeout 15 tailcat ssh "$addr3" 'echo combo-ssh-ok' 2>&1)"
  assert_contains "$ssh_out" "combo-ssh-ok" "combined serve: no-auth-ssh also works in the same server"
fi
pkill tailcat >/dev/null 2>&1 || true
pkill -f "http.server 18082" >/dev/null 2>&1 || true

exit_with_summary
