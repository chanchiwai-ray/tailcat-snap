#!/usr/bin/env bash
# recv (flat drop-box) and recv --accept-dirs (recursive drop-box).
set -u
cd "$(dirname "${BASH_SOURCE[0]}")"
source ./lib.sh
require_tailcat

# --- recv (flat, default) ---
mkdir -p "$WORKDIR/inbox"
timeout 25 tailcat recv "$WORKDIR/inbox" > "$WORKDIR/recv_server.log" 2>&1 &
disown
addr="$(wait_for_addr "$WORKDIR/recv_server.log" 10)"
if [[ -z "$addr" ]]; then
  fail "recv setup: server never printed an address"
else
  assert_contains "$WORKDIR/recv_server.log" "write-only" "recv announces a write-only drop box"
  echo "dropped file $(date +%s)" > "$WORKDIR/drop.txt"
  timeout 15 tailcat cp "$WORKDIR/drop.txt" "$addr:" >/dev/null 2>&1
  rc=$?
  assert_exit_code "$rc" 0 "recv accepts an upload"
  # Flat mode saves under a server-chosen unique name, not the
  # original filename -- so just check *some* file landed.
  n="$(find "$WORKDIR/inbox" -type f 2>/dev/null | wc -l)"
  if [[ "$n" -ge 1 ]]; then
    pass "recv: uploaded file appears in the inbox directory (server-chosen name)"
  else
    fail "recv: no file appeared in the inbox directory"
  fi
fi
pkill tailcat >/dev/null 2>&1 || true
sleep 1

# --- recv --accept-dirs (recursive) ---
mkdir -p "$WORKDIR/inbox_dirs" "$WORKDIR/docs/sub"
echo "d1" > "$WORKDIR/docs/x.txt"
echo "d2" > "$WORKDIR/docs/sub/y.txt"
timeout 25 tailcat recv --accept-dirs "$WORKDIR/inbox_dirs" > "$WORKDIR/recv_dirs_server.log" 2>&1 &
disown
addr2="$(wait_for_addr "$WORKDIR/recv_dirs_server.log" 10)"
if [[ -z "$addr2" ]]; then
  fail "recv --accept-dirs setup: server never printed an address"
else
  timeout 15 tailcat cp -r "$WORKDIR/docs" "$addr2:docs" >/dev/null 2>&1
  rc=$?
  assert_exit_code "$rc" 0 "recv --accept-dirs accepts a recursive upload"
  assert_file_exists "$WORKDIR/inbox_dirs/docs/x.txt" "recv --accept-dirs: top-level file kept its name"
  assert_file_exists "$WORKDIR/inbox_dirs/docs/sub/y.txt" "recv --accept-dirs: nested file kept its name"
fi
pkill tailcat >/dev/null 2>&1 || true

exit_with_summary
