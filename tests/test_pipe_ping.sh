#!/usr/bin/env bash
# Basic stdin/stdout pipe (default server mode), ping, --json, and the
# TAILCAT_ADDR_FILE environment variable (both plain-path and tcp: modes).
set -u
cd "$(dirname "${BASH_SOURCE[0]}")"
source ./lib.sh
require_tailcat

# --- basic pipe round trip ---
timeout 30 tailcat > "$WORKDIR/server.log" 2>&1 &
disown
addr="$(wait_for_addr "$WORKDIR/server.log" 10)"
if [[ -z "$addr" ]]; then
  fail "server never printed an address"
else
  msg="hello from test_pipe_ping $(date +%s)"
  echo "$msg" | timeout 20 tailcat "$addr" >/dev/null 2>&1
  client_exit=$?
  assert_exit_code "$client_exit" 0 "client exits 0 after sending its message"
  sleep 1
  assert_contains "$WORKDIR/server.log" "$msg" "server log contains the client's message"
fi
pkill tailcat >/dev/null 2>&1 || true
sleep 1

# --- ping ---
timeout 20 tailcat > "$WORKDIR/server2.log" 2>&1 &
disown
addr2="$(wait_for_addr "$WORKDIR/server2.log" 10)"
if [[ -z "$addr2" ]]; then
  fail "ping setup: server never printed an address"
else
  out="$(timeout 15 tailcat ping "$addr2" 2>&1)"
  assert_contains "$out" "pong in" "ping receives a pong"
fi
pkill tailcat >/dev/null 2>&1 || true
sleep 1

# --- --json flag ---
timeout 15 tailcat --json > "$WORKDIR/server_json.log" 2>&1 &
disown
sleep 4
assert_contains "$WORKDIR/server_json.log" '"listenAddr"' "--json writes a listenAddr JSON line to stdout"
pkill tailcat >/dev/null 2>&1 || true
sleep 1

# --- TAILCAT_ADDR_FILE (plain path) ---
rm -f "$WORKDIR/addr.txt"
TAILCAT_ADDR_FILE="$WORKDIR/addr.txt" timeout 15 tailcat > "$WORKDIR/server3.log" 2>&1 &
disown
addr3="$(wait_for_addr "$WORKDIR/server3.log" 10)"
assert_file_exists "$WORKDIR/addr.txt" "TAILCAT_ADDR_FILE wrote a file"
if [[ -f "$WORKDIR/addr.txt" ]]; then
  written="$(cat "$WORKDIR/addr.txt")"
  assert_eq "$written" "$addr3" "TAILCAT_ADDR_FILE file content matches the printed address"
fi
pkill tailcat >/dev/null 2>&1 || true
sleep 1

# --- TAILCAT_ADDR_FILE (tcp: mode) ---
python3 - "$WORKDIR/tcp_recv.log" <<'PYEOF' &
import socket, sys
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind(("127.0.0.1", 0))
port = s.getsockname()[1]
with open(sys.argv[1] + ".port", "w") as f:
    f.write(str(port))
s.listen(1)
conn, _ = s.accept()
data = conn.recv(4096)
with open(sys.argv[1], "w") as f:
    f.write(data.decode().strip())
conn.close()
PYEOF
disown
# Wait for the listener to publish its port.
for i in $(seq 1 20); do
  [[ -f "$WORKDIR/tcp_recv.log.port" ]] && break
  sleep 0.3
done
tcp_port="$(cat "$WORKDIR/tcp_recv.log.port" 2>/dev/null || echo "")"
if [[ -z "$tcp_port" ]]; then
  fail "TAILCAT_ADDR_FILE tcp: setup: listener never published its port"
else
  TAILCAT_ADDR_FILE="tcp:127.0.0.1:$tcp_port" timeout 15 tailcat > "$WORKDIR/server4.log" 2>&1 &
  disown
  addr4="$(wait_for_addr "$WORKDIR/server4.log" 10)"
  sleep 1
  if [[ -f "$WORKDIR/tcp_recv.log" ]]; then
    received="$(cat "$WORKDIR/tcp_recv.log")"
    assert_eq "$received" "$addr4" "TAILCAT_ADDR_FILE tcp: mode sent the matching address"
  else
    fail "TAILCAT_ADDR_FILE tcp: mode: listener never received anything"
  fi
fi
pkill tailcat >/dev/null 2>&1 || true

exit_with_summary
