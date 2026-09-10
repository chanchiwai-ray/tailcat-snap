# Security

This is an unopinionated snap package for [tailcat](https://github.com/tailscale/tailcat). Most of
the security issues should be reported directly to the upstream project unless it's related to the
snap package itself.

The [threat model](https://github.com/tailscale/tailcat/blob/main/SECURITY.md) also mostly inherit
from the upstream project, but the snap packaging itself may introduce additional security layer
due to the level of confinement and the snapd security model.

## Notable security differences from upstream binary

Since this snap package is strictly confined, it has additional apparmor profiles enforced by
`snapd` to enhance the security. Below are the list of additional limitation (or security features)
that are not present in the upstream binary:

- `tailcat ssh` will only have access to the server's `$HOME` directory and will not have access to
  other users' home directories or system files or `/tmp`.
- `tailcat ssh` will create an interactive shell session with only a curated set of coreutils or
  shell binaries; any binary not on that allowlist (e.g. `whoami`) is denied even though it exists
  on the host.
- `tailcat cp`, `tailcat recv`, and `tailcat serve --files` can only read/write files under the
  real, host `$HOME` directory (excluding dotfiles/dot-directories and the snap's own
  `~/snap/tailcat/` data dir); paths outside `$HOME`, such as `/tmp` or another user's home
  directory, are not visible to the snap at all.
- `tailcat genkey` and other commands that rely on the `$HOME` environment variable (rather than
  the real home directory) will store their data under `~/snap/tailcat/<revision>/...` instead of
  the upstream-documented path; these files are private to the snap (`0700` permissions).
- `tailcat socks <addr> <cmd>` can only exec binaries bundled with the snap (similiar to `tailcat ssh`),
  so most external tools (e.g. `curl`) cannot be run directly as `<cmd>`.

For details of those limitations, please refer to the [Known issues](./docs/known_issues.md)
section.
