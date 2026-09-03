# Available Features (Verified Working Under Strict Confinement)

This document lists the `tailcat` functionality that was manually verified to work correctly when
installed as a strictly confined snap (`confinement: strict`) with only the `home`, `network`, and
`network-bind` plugs connected -- the default, auto-connected set for this package. Every
subcommand and flag in `tailcat --help` is covered here or in
[`known_issues.md`](./known_issues.md). See [`../tests/`](../tests/) for automated scripts that
reproduce these checks, and [`../CONTRIBUTING.md`](../CONTRIBUTING.md) for how to run them.

## CLI basics

- `tailcat --help` -- prints usage.
- `tailcat --version` / `tailcat version` -- both print the build
  version (e.g. `v0.5.1-0.20260903013319-476c217fa9fa+dirty`).
- `tailcat readme` -- prints the full upstream README.
- `tailcat printpub` -- prints the public key of the client key that
  would be used (the ephemeral key, or a saved `client-default` key).
- `tailcat parse <tc-addr>` -- decodes an address and prints its
  fields as JSON (`ServerPublic`, `ServerDiscoPublic`, `RegionID`, ...).
- `tailcat resolve <tc-addr>` -- expands a short address into a longer
  one with the DERP region's node info embedded, so a client doesn't
  need to fetch the DERP map separately.
- `snap connections tailcat` -- shows `home`, `network`, and
  `network-bind` auto-connected, as declared in `snapcraft.yaml`.

## Networking (DERP + WireGuard tunnel)

All of the following were verified to actually move traffic over Tailscale's real, public DERP
relay network (region resolved to Frankfurt in this environment) and establish a working WireGuard
tunnel entirely in userspace, with no root/admin privileges and no kernel TUN/TAP device required:

- **Basic stdin/stdout pipe (default server mode).**
  Server: `tailcat` prints a fresh ephemeral address and waits.
  Client: `echo "<message>" | tailcat <tc-addr>` delivers the message,
  which appears verbatim on the server's stdout. Verified with a live round trip:

  ```txt
  hello from tailcat client Thu Sep  3 04:19:25 UTC 2026
  ```

- **`tailcat ping <tc-addr>`.**
  Successfully pinged a locally running server through the tunnel:

  ```txt
  pong in 478.6ms via DERP(fra)
  ```

- **`tailcat serve <port>` (single port forwarded to localhost).**
  Started a local `python3 -m http.server 8080`, served it with `tailcat serve 8080`, then fetched
  it from a separate `tailcat` client process using a raw HTTP request piped over the tunnel:

  ```txt
  $ echo -e "GET / HTTP/1.0\r\nHost: local\r\n\r\n" | tailcat <tc-addr> 8080
  HTTP/1.0 200 OK
  Server: SimpleHTTP/0.6 Python/3.10.12
  ...
  ```

- **`tailcat serve all` (every port).**
  Same as above but with `serve all` instead of naming port 8080 explicitly -- the client connected
  to port 8080 without the server having named it, confirming all-ports mode works.

- **`tailcat serve <port>,no-auth-ssh` (combined services).**
  A single server serving both a forwarded port and the auth-free SSH service simultaneously; both
  worked in the same run (`tailcat <addr> <port>` for the HTTP fetch, `tailcat ssh <addr> <cmd>`
  for the shell command).

- **`tailcat serve exit-node` + `tailcat socks`/`tailcat ssh -p ip:port` (routing through an exit node).**
  A server run with `--serve=exit-node` correctly proxies arbitrary destinations, not just its own
  local ports:
  - Via `tailcat socks <exit-node-addr>` + `curl --socks5-hostname ... https://example.com/`:
    got a real `200` from the public internet, routed entirely through the exit-node server's own
    network connection.
  - Via `tailcat ssh -p 127.0.0.1:22 <exit-node-addr> ...`: the
    connection reached the exit-node host's real `sshd` (confirmed by receiving a genuine
    `Permission denied (publickey)` response -- the actual SSH protocol banner/handshake --
    rather than a connection error), proving the TCP route through the exit node works.
    (Completing a real login additionally requires valid host SSH credentials, which is a
    test-environment limitation, not a packaging or tailcat issue.)

- **`tailcat forward <tc-addr> <[local:]remote>`.**
  Forwarded a local port to a `tailcat serve <port>` target (`tailcat forward <addr> 0:8091` for an
  OS-assigned local port) and fetched it with `curl` on the forwarded local port, receiving a real
  `200`.

- **`tailcat socks` (SOCKS5 proxy).**
  Ran `tailcat socks <tc-addr>` (daemon mode, prints its listen address) and drove it with an
  external `curl --socks5-hostname`:
  - `http://server.tailcat:<port>/` (the magic hostname meaning "the
     server named by the `<tc-addr>` argument") -- `200`.
  - `http://<tc-addr>:<port>/` (the tc-addr used directly as the
     SOCKS5 destination hostname) -- `200`.
  - See the exit-node bullet above for `socks` combined with
    `--serve=exit-node`, reaching the open internet.

- **`--allow=<pubkey>` (client allowlisting).**
  A server started with `--allow=<client-pubkey>` (from `tailcat genkey --client`) accepted a
  client using the matching `--key`, and timed out (never established) a client using a different,
  unlisted key -- confirming the allowlist is enforced.

- **`--full-address` / `tailcat resolve`.**
  `tailcat serve --full-address` prints an address with the DERP node info embedded directly (same
  effect as running plain `tailcat resolve <short-addr>` afterwards); both produce a working,
  longer address.

- **`--json` (server mode).**
  `tailcat --json` additionally writes `{"listenAddr": "tco..."}` as a single JSON line to stdout,
  alongside the normal human-readable banner on stderr.

## Key management

- **`tailcat genkey --key=<name>`.**
  Generates and saves a persistent WireGuard keypair, printing its tailcat address. Works correctly
  under confinement, though the file ends up under the snap's private data directory rather than
  the literal `$HOME/.config/tailcat` path from upstream docs -- see
  [`known_issues.md`](./known_issues.md#1-genkey-writes-to-the-snaps-private-data-directory-not-home)
  for the exact path and details.
- **`tailcat genkey --list`.**
  Correctly lists previously saved key names.
- **`tailcat genkey --delete --key=<name>`.**
  Correctly removes a saved key; a subsequent `--list` no longer shows it.
- **`tailcat genkey --client --key=<name>`.**
  Generates a client identity key (no DERP region) and prints its public key (`nodekey:...`), for
  use in a server's `--allow` list -- confirmed working end-to-end with the `--allow` test above.
- **`tailcat genkey --region=list`.**
  Prints the table of known DERP regions (ID, code, name).
- **`tailcat genkey --key=<name> --region=<code>`.**
  Bakes a specific region (e.g. `fra`) into the key/address instead of auto-selecting by latency.
- **`tailcat genkey --key=<name> --fixed-region`.**
  Probes the nearest region once, now, and bakes that choice in.
- **`tailcat genkey --key=<name> --embed-derp-map --region=<code>`.**
  Works correctly **when `--region` is given explicitly**. See
  [`known_issues.md`](./known_issues.md#5-genkey---embed-derp-map-panics-with-the-default---regionauto)
  for a real upstream crash when `--embed-derp-map` is combined with the default `--region=auto`.

## File serving (within `$HOME`)

- **`tailcat recv <dir>`**
  `<dir>` is a path under the real `$HOME` (e.g. `~/tailcat_inbox`), starts a write-only drop-box
  file server and prints its tailcat address, e.g.:

  ```
  # Serving files from /home/sandbox/tailcat_inbox (flat write-only)
  # 🐈 Server listening with new address: tco2FwWCAu1D-...
  ```

  This confirms the `home` plug is sufficient for serving/receiving files as long as the target
  directory lives inside the user's home tree. (Paths outside `$HOME`, such as `/tmp`, do **not**
  work under strict confinement -- see `known_issues.md`.)

- **`tailcat recv --accept-dirs <dir>`.**
  Same as above but accepts recursive directory uploads (`tailcat cp -r`), preserving the sender's
  file/directory names, equivalent to `serve --files=<dir>:wo+ files` below.

- **`tailcat serve --files=<dir>:ro files` (read-only, the default).**
  Served a directory read-only; `tailcat ls`/`tailcat cp <addr>:file` (fetch) both worked; a
  `tailcat cp <local> <addr>:` (upload attempt) was correctly rejected with a permission error.

- **`tailcat serve --files=<dir>:rw files` (read-write).**
  Uploaded a file with `tailcat cp`, confirmed it landed with its original name and content, and
  that `tailcat ls` lists it afterwards.

- **`tailcat serve --files=<dir>:wo+ files` (recursive write-only drop box).**
  Uploaded a directory tree with `tailcat cp -r ./photos <addr>:photos` and confirmed the full tree
  (including a nested subdirectory) landed intact with original names; `tailcat ls` against the
  root was correctly rejected (write-only, no listing).

- **`tailcat ls [-l] <tc-addr>[:path]`.**
  Listed a served directory's contents; `-l` produced a long-format listing (permissions, size,
  modification time) via SFTP directly (no separate `ssh`/`sftp` binary invoked for this
  subcommand).

## File copy and remote shell (`cp`, `ssh`)

Both subcommands work by exec'ing the system `scp`/`ssh` with a `ProxyCommand` that re-invokes
`tailcat` itself for the tunnel transport. The part now stages `openssh-client` (`stage-packages:
[openssh-client]`) and uses a `layout` bind-mount to satisfy `scp`'s compile-time hardcoded path to
`ssh`; see
[`known_issues.md`](./known_issues.md#3-tailcat-cptailcat-ssh-client-side-fixed-by-bundling-openssh--a-layout-bind-mount)
for the full before/after and why the fix needed two parts.

- **`tailcat cp <local-file> <tc-addr>:`** / **`tailcat cp -r`** / **`tailcat cp -p`.**
  Copied files and directory trees to/from `tailcat recv`/`serve --files` targets in both
  directions and confirmed exact content matches; see the file-serving section above for the
  `:ro`/`:rw`/ `:wo+` mode-specific results.

- **`tailcat ssh <tc-addr> <command>`.**
  Ran commands against a `tailcat serve no-auth-ssh` target and confirmed the session is a genuine
  shell running in the *server's* real home directory (not a snap-private path), matching
  upstream's documented behavior:

  ```
  $ tailcat ssh "$ADDR" 'pwd; id; ls -la'
  /home/sandbox
  uid=1000(sandbox) gid=1000(sandbox) groups=1000(sandbox),27(sudo)
  total 72
  drwxr-x--- 10 sandbox sandbox 4096 Sep  3 04:49 .
  ...
  ```

  Caveat: only a curated allowlist of coreutils/shell binaries can be exec'd inside that remote
  shell (e.g. `whoami` fails) -- see `known_issues.md` for details. This is a pre-existing property
  of snapd's default strict-confinement template, unrelated to the `cp`/`ssh` fix itself.

## Environment variables

- **`TAILCAT_ADDR_FILE=<path>`.**
  Server mode wrote its tailcat address to the given file path, verified with matching content.
- **`TAILCAT_ADDR_FILE=tcp:<host>:<port>`.**
  Server mode connected to the given TCP address and sent its tailcat address as a line of text,
  verified by a listener that received the exact address.
- **`TAILCAT_DERPMAP_URL`.**
  Not separately exercised beyond the default; equivalent to `--derpmap-url` (untested override,
  low risk -- both just set the same URL string consumed by the same code path already exercised
  via the default).

## Summary

Under the snap's current strict-confinement plug set (`home`, `network`, `network-bind`), plus a
bundled `openssh-client` and a `layout` bind-mount, essentially all of tailcat's documented
functionality works correctly and was verified against the real, public DERP relay infrastructure,
including exit-node traffic routing and the SOCKS5 proxy. The remaining caveats are narrow and
documented in `known_issues.md`: `genkey`'s storage path differs from upstream docs (an env-var
remapping, not a filesystem restriction), file-serving paths must be under the real `$HOME`, only
an allowlisted set of system binaries can be exec'd inside a remote `ssh` shell session, and a real
upstream crash in `genkey --embed-derp-map` when combined with the default `--region=auto`.
