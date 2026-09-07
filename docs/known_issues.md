# Known Issues (Strict Confinement)

This document lists behaviors observed while testing the `tailcat` snap under `confinement: strict`
with only the `home`, `network`, and `network-bind` plugs connected (see [`../tests/`](../tests/)
for the automated pytest suite that reproduces these checks). It separates what works from what
doesn't, with the underlying cause for each failure.

## Summary table

| Feature | Works under strict confinement? | Notes |
|---|---|---|
| `tailcat` (basic stdin/stdout pipe) | ✅ Yes | |
| `tailcat ping` | ✅ Yes | |
| `tailcat serve <port>` / `serve all` / combined services | ✅ Yes | |
| `tailcat serve exit-node` + `socks`/`ssh -p ip:port` | ✅ Yes | Full traffic routing verified, including to the open internet |
| `tailcat socks` | ✅ Yes | Except execing `curl`/other external tools as `<cmd>` -- see #6 |
| `tailcat forward` | ✅ Yes | |
| `tailcat ls` / `parse` / `resolve` / `printpub` / `version` / `readme` | ✅ Yes | |
| `--allow` (client allowlisting) | ✅ Yes | |
| `--full-address` / `--json` | ✅ Yes | |
| `tailcat genkey` | ⚠️ Partially | Works, but writes keys under the snap's private data dir, not the real `$HOME/.config/tailcat` upstream docs describe |
| `tailcat recv <dir>` / `tailcat serve --files` | ⚠️ Partially | Only works for paths under the real `$HOME`; fails for paths elsewhere (e.g. `/tmp`) |
| `tailcat cp` | ✅ Yes | Requires bundling `openssh-client` plus a `layout` bind-mount for `scp`'s hardcoded `ssh` path (see `snap/snapcraft.yaml`). Local-side paths must also be under `$HOME` (same `home`-plug restriction as `recv`) |
| `tailcat ssh` (run a remote command) | ✅ Yes | Same requirements as `cp`. Lands the session in the server's real `$HOME`, as documented in the source (`newSessionCommand` sets `cmd.Dir = u.HomeDir`) |
| `tailcat ssh`/server-side shell: arbitrary coreutils | ⚠️ Partially | Only a curated allowlist of coreutils/utilities is exec-able inside an interactive shell session on the confined server (e.g. `ls`, `id`, `bash` work; `whoami` does not) |
| `tailcat socks <addr> curl ...` (execing external tools) | ❌ No | `curl` (and most non-bundled system tools) aren't visible inside the snap's confined filesystem view at all -- see #6 |

## Details

### 1. `genkey` writes to the snap's private data directory, not `$HOME`

Upstream docs (and `tailcat --help`) say keys are saved to
`~/.config/tailcat/keys/<name>.private.json`. Under strict confinement with the `home` interface,
snapd remaps `$HOME` for the process to the snap's own per-revision data directory, so the key
actually lands at:

```txt
~/snap/tailcat/x1/.config/tailcat/keys/testkey.private.json
```

instead of `~/.config/tailcat/keys/testkey.private.json`. This is standard, expected snap behavior
(all snap apps store their normal "$HOME/..." data under `~/snap/<name>/<revision>/...` and the
latest revision is also reachable via `~/snap/<name>/current/...`), but it's worth calling out
explicitly because it means:

- Keys are **not** where the upstream README says they'll be.
- Users following the upstream docs verbatim (e.g. scripting around
  `~/.config/tailcat/keys/default.private.json`) need to adjust the path when using the snap.
- Keys are, however, private to the snap ((mode `0700` files under a
  `0700` directory) so this does not weaken security, just changes the path.

Reproduced with:

```sh
tailcat genkey --key=testkey
# wrote file to /home/sandbox/snap/tailcat/x1/.config/tailcat/keys/testkey.private.json
```

### 2. File-serving subcommands (`recv`, `serve --files`) only work under `$HOME`

The `home` plug only grants access to the user's actual home directory tree (and, transparently,
the snap's own data dir under it). Paths outside `$HOME` -- such as `/tmp`, another user's home, or
an arbitrary mount point -- are not visible inside the snap's mount namespace at all, so operations
against them fail with a generic "no such file or directory", which can be misleading (it looks
like a missing directory, not a permissions/visibility problem):

```sh
$ tailcat recv /tmp/inbox
# Selected bootstrap relay region 303, Frankfurt
2026/09/03 04:22:06 --files: stat /tmp/inbox: no such file or directory
```

The same directory worked fine once it was under `$HOME`:

```sh
$ mkdir -p ~/tailcat_inbox
$ tailcat recv ~/tailcat_inbox
# Selected bootstrap relay region 303, Frankfurt
# Serving files from /home/sandbox/tailcat_inbox (flat write-only)
# 🐈 Server listening with new address: tco2FwWCAu1D-kMLtoRwVsfSSuCCWIg28Sf_1hSxVpBc00L9reBmFrWCCgFtq-e37nNqIb1PE-tDKjIvlDJubcIKS-W6gP0ojMd2FpGQEv
```

**Implication for packaging:** if broader filesystem access is a desired use case (e.g. serving
arbitrary directories, not just ones under `$HOME`), the snap would need additional interfaces such
as `removable-media` and/or `system-files`, and users would need to manually connect them (`snap
connect tailcat:removable-media`), since they don't auto-connect under strict confinement.

### 3. `tailcat cp`/`tailcat ssh` (client side): requires bundling OpenSSH + a `layout` bind-mount

Per upstream docs, `tailcat cp` "runs the system `scp`" and `tailcat ssh` "execs the system ssh
client," both via a `ProxyCommand` that re-invokes `tailcat` itself for the actual tunnel
transport. Strict confinement's AppArmor profile does not allow the snap to exec arbitrary binaries
outside its own confined content, so the base system's `scp`/`ssh` aren't usable. `snap/snapcraft.yaml`
addresses this by staging `openssh-client` inside the snap's own content (so exec'ing the bundled
`ssh`/`scp` is permitted) and by adding a `layout` bind-mount for `scp`'s compile-time hardcoded
`/usr/bin/ssh` path onto the bundled `ssh` binary -- see the comments in `snapcraft.yaml` for the
full rationale.

With both in place, `tailcat cp` and `tailcat ssh` (running a remote command) both work correctly,
and `tailcat ssh` lands the session in the server's real (host) `$HOME`, matching the source
(`tailcat_ssh_unix.go`'s `newSessionCommand` sets `cmd.Dir = u.HomeDir`):

```sh
$ tailcat ssh "$ADDR" 'pwd; id; ls -la'
/home/sandbox
uid=1000(sandbox) gid=1000(sandbox) groups=1000(sandbox),27(sudo)
total 72
drwxr-x--- 10 sandbox sandbox 4096 Sep  3 04:49 .
...
```

**Remaining caveat:** the interactive shell session on the server is still bound by the same
strict-confinement AppArmor rules as everything else run by this snap. A curated allowlist of
common coreutils/shell binaries (`bash`, `dash`, `ls`, and dozens more) is permitted, but not every
system binary -- e.g. `whoami` is not on that allowlist and fails inside an SSH session:

```
$ tailcat ssh "$ADDR" whoami
/bin/bash: line 1: /usr/bin/whoami: Permission denied
```

This is a pre-existing property of snapd's default strict-confinement template (the same allowlist
that already permitted `bash`/`ls`/etc. without any packaging changes), and there's no complete
workaround short of running an unconfined (non-snap) `tailcat`, or `stage-packages`-bundling every
individual tool a user might want to run remotely (impractical).

Also observed: `ssh` logs one harmless AppArmor denial per invocation for a system-wide config file
it optionally reads and continues without (`/etc/ssh/ssh_config`); this did not affect any observed
test outcome.

**Also note:** like `recv`/`serve --files` (issue #2), `tailcat cp`'s *local*-side path (the
non-`<tc-addr>:` argument) must be under the real `$HOME` too, since `scp` runs inside the same
confined process. A local source/destination under `/tmp` fails opaquely:

```sh
$ tailcat cp /tmp/hack.txt "$ADDR":
/snap/tailcat/x1/usr/bin/scp: stat local "/tmp/hack.txt": No such file or directory
```

while the identical command with the local file under `$HOME` works normally.

### 4. Filesystem access: real `$HOME` vs. the `$HOME` env var

These are two different things and it's easy to conflate them (this document's own earlier drafts
did):

- **The `home` interface's filesystem grant is the real, host `$HOME`**
  (e.g. `/home/username/...`), not a snap-private directory. Confirmed directly from this snap's
  generated AppArmor profile (`/var/lib/snapd/apparmor/profiles/snap.tailcat.tailcat`):

  ```
  # Note, @{HOME} is the user's $HOME, not the snap's $HOME
  owner @{HOME}/ r,
  owner @{HOME}/[^s.]**  rwklix,
  ```

  It grants read/write to everything under the real `$HOME` **except** `@{HOME}/snap/**` (reserved
  for the snap's own data) and toplevel hidden/dotfiles/dot-directories (the `[^s.]` pattern
  excludes names starting with `.`). This is why `~/tailcat_inbox` (non-hidden, real `$HOME`)
  worked in issue #2 above, while `/tmp/...` (outside `$HOME` entirely) did not -- and it's also
  why `tailcat ssh`'s remote shell session, above, could `ls -la`/`cat` real files under
  `/home/sandbox/...`.

- **The `$HOME` environment variable** the confined process itself
  sees is a *separate*, unrelated remapping done by snapd: it's set to
  `~/snap/tailcat/<revision>/`, not the real `$HOME`. This only matters for code that builds
  paths by reading `$HOME` from its own environment (e.g. Go's `os.UserConfigDir()`, or
  `ssh`/`scp` resolving `~/.ssh/config`) -- which is exactly why `genkey` (issue #1 above) landed
  under `~/snap/tailcat/x1/.config/...` rather than the literal `~/.config/...` path from
  upstream docs, even though the real `~/.config/` directory itself is otherwise fully
  visible/writable to the snap under the interface grant described above.

**Practical takeaway:** sharing an arbitrary file under the real home directory (e.g.
`/home/username/abc.txt`) already works today with no packaging changes, as long as tailcat is
given the literal absolute path (or `~/abc.txt`, since the invoking shell -- not the confined
process -- expands `~` before tailcat ever sees the argument). Only paths outside `$HOME` entirely,
or dotfiles/dot-directories directly under it, are actually restricted.

### 5. `tailcat socks <addr> <cmd>` can't run most external tools (e.g. `curl`) as `<cmd>`

`tailcat socks`'s documented examples include running a `<cmd>` (like `curl`) as a child process
with the proxy's address in its `all_proxy` environment variable. Under strict confinement, this
fails for any tool that isn't part of the snap's own bundled content or the `core24` base snap,
because it simply isn't visible inside the snap's confined filesystem view at all -- not an
AppArmor exec denial, but the path not existing:

```sh
$ tailcat socks <tc-addr> curl http://server.tailcat:8095/
2026/09/03 07:14:23 exec: "curl": executable file not found in $PATH

$ snap run --shell tailcat -c 'stat /usr/bin/curl'
stat: cannot statx '/usr/bin/curl': No such file or directory
```

(Confirmed no AppArmor denial in `dmesg` for this -- it's a plain "file doesn't exist" from Go's
`exec.LookPath`, since `/usr/bin/curl` on the host simply isn't part of the snap's own content or
the base snap's, and strict confinement doesn't expose arbitrary host binaries into the snap's
mount namespace.)

**Workaround:** run `tailcat socks` without a `<cmd>` (daemon mode, `tailcat socks <tc-addr>`,
which just prints its listen address) and point an unconfined tool's SOCKS5 proxy setting (e.g.
`curl --socks5-hostname 127.0.0.1:<port> ...`) at it from *outside* the snap -- this was used
throughout this project's own SOCKS testing and works correctly, including for exit-node routing to
the open internet (see `available_features.md`). The same `stage-packages` bundling approach used
for `openssh-client` (issue #3) could in principle bundle `curl` too, if execing it as a direct
`<cmd>` child of the confined `tailcat` process were a hard requirement.

### 6. Redirecting the confined process's own stdout to a file fails silently inside an unprivileged LXD container

Discovered while building the two-container functional test suite under [`../tests/`](../tests/)
(each "client"/"server" is a separate, unprivileged LXD container so they have genuinely distinct
network namespaces). A direct shell redirect of `tailcat`'s own output to a regular file --
`tailcat ... > logfile 2>&1` -- silently produces a **0-byte** logfile: the process still runs
normally and exits 0, it just never manages to write anything, anywhere.

**Root cause** (confirmed via `dmesg`/`journalctl -k` inside the container's LXD host): this is
`snap-confine`'s *own* AppArmor profile -- not `tailcat`'s app-level confinement, which never even
gets a chance to run -- denying `file_inherit` for a write fd pointing at a regular file, specific
to the uid-shifted namespace an unprivileged container maps its "root" user to:

```
apparmor="DENIED" operation="file_inherit" profile="/usr/lib/snapd/snap-confine"
name="/root/f1.log" requested_mask="w" denied_mask="w" fsuid=1000000 ouid=1000000
```

(`fsuid=1000000`/`ouid=1000000` is the classic signature of LXD's default unprivileged
uid-shifting -- container "root" maps to host uid 1000000+.) The shell (`bash`, unconfined) opens
the destination file fine; the problem is specifically `snap-confine` refusing to let the about-to-
be-confined child *inherit* that already-open write fd once it detects this uid-shifted context.

**Workaround:** pipe through an intermediate, unconfined process instead of a direct file redirect,
e.g.:

```sh
tailcat ... 2>&1 | tee logfile > /dev/null
```

This way the confined process's own stdout fd is a **pipe** (which `snap-confine`'s `file_inherit`
policy does allow), while the actual regular-file `open()` happens in `tee`, which is never
confined. This is exactly what [`../tests/functional/helpers.py`](../tests/functional/helpers.py)'s
`run_bg()` does, and is the only reason the (otherwise identical) bash smoke-test suite this project
used before didn't hit this: those tests ran directly on a single host with a normal (non-uid-
shifted) root user, not inside a nested unprivileged container.

**Scope:** this is specific to running a strict-confinement snap inside an *unprivileged* LXD
container (or likely any other uid-shifted user-namespace sandbox); it does not affect normal
installs on a real machine or VM, and is unrelated to anything in this project's own
`snap/snapcraft.yaml` packaging.
