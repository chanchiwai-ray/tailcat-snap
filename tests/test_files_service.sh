#!/usr/bin/env bash
# serve --files=<dir>[:ro|:rw|:wo+], ls, and cp (fetch/upload/recursive).
set -u
cd "$(dirname "${BASH_SOURCE[0]}")"
source ./lib.sh
require_tailcat

# --- :ro (read-only, the default) ---
mkdir -p "$WORKDIR/files_ro"
echo "readonly content" > "$WORKDIR/files_ro/readme.txt"
timeout 25 tailcat serve --files="$WORKDIR/files_ro:ro" files > "$WORKDIR/ro_server.log" 2>&1 &
disown
addr="$(wait_for_addr "$WORKDIR/ro_server.log" 10)"
if [[ -z "$addr" ]]; then
  fail ":ro setup: server never printed an address"
else
  out="$(timeout 15 tailcat ls "$addr" 2>&1)"
  assert_contains "$out" "readme.txt" "ls lists the read-only served file"

  timeout 15 tailcat cp "$addr:readme.txt" "$WORKDIR/fetched_readme.txt" >/dev/null 2>&1
  assert_file_exists "$WORKDIR/fetched_readme.txt" "cp fetches a file from the :ro server"
  if [[ -f "$WORKDIR/fetched_readme.txt" ]]; then
    assert_eq "$(cat "$WORKDIR/fetched_readme.txt")" "readonly content" "fetched file content matches"
  fi

  echo "should not be writable" > "$WORKDIR/hack.txt"
  timeout 15 tailcat cp "$WORKDIR/hack.txt" "$addr:" >/dev/null 2>&1
  rc=$?
  if [[ "$rc" -ne 0 ]]; then
    pass ":ro server correctly rejects an upload attempt"
  else
    fail ":ro server unexpectedly accepted an upload"
  fi
fi
pkill tailcat >/dev/null 2>&1 || true
sleep 1

# --- :rw (read-write) ---
mkdir -p "$WORKDIR/files_rw"
timeout 25 tailcat serve --files="$WORKDIR/files_rw:rw" files > "$WORKDIR/rw_server.log" 2>&1 &
disown
addr2="$(wait_for_addr "$WORKDIR/rw_server.log" 10)"
if [[ -z "$addr2" ]]; then
  fail ":rw setup: server never printed an address"
else
  echo "rw upload $(date +%s)" > "$WORKDIR/rw_upload.txt"
  timeout 15 tailcat cp "$WORKDIR/rw_upload.txt" "$addr2:" >/dev/null 2>&1
  rc=$?
  assert_exit_code "$rc" 0 ":rw server accepts an upload"
  assert_file_exists "$WORKDIR/files_rw/rw_upload.txt" ":rw uploaded file exists with its original name"
  out="$(timeout 15 tailcat ls "$addr2" 2>&1)"
  assert_contains "$out" "rw_upload.txt" ":rw server's ls sees the uploaded file"
fi
pkill tailcat >/dev/null 2>&1 || true
sleep 1

# --- :wo+ (recursive write-only drop box) ---
mkdir -p "$WORKDIR/files_wop" "$WORKDIR/photos/sub"
echo "photo1" > "$WORKDIR/photos/a.txt"
echo "photo2" > "$WORKDIR/photos/sub/b.txt"
timeout 25 tailcat serve --files="$WORKDIR/files_wop:wo+" files > "$WORKDIR/wop_server.log" 2>&1 &
disown
addr3="$(wait_for_addr "$WORKDIR/wop_server.log" 10)"
if [[ -z "$addr3" ]]; then
  fail ":wo+ setup: server never printed an address"
else
  timeout 15 tailcat cp -r "$WORKDIR/photos" "$addr3:photos" >/dev/null 2>&1
  rc=$?
  assert_exit_code "$rc" 0 ":wo+ server accepts a recursive directory upload (cp -r)"
  assert_file_exists "$WORKDIR/files_wop/photos/a.txt" ":wo+ top-level file landed with its original name"
  assert_file_exists "$WORKDIR/files_wop/photos/sub/b.txt" ":wo+ nested file landed with its original name"

  timeout 15 tailcat ls "$addr3" >/dev/null 2>&1
  rc=$?
  if [[ "$rc" -ne 0 ]]; then
    pass ":wo+ server correctly rejects listing (write-only)"
  else
    fail ":wo+ server unexpectedly allowed listing"
  fi
fi
pkill tailcat >/dev/null 2>&1 || true

exit_with_summary
