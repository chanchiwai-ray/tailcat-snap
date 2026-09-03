# Contributing

## Prerequisites

- [snapcraft](https://snapcraft.io/docs/snapcraft-overview) -- follow
  the official install instructions for your platform.
- A build provider snapcraft can use (e.g.
  [LXD](https://documentation.ubuntu.com/lxd/en/latest/installing/) or
  Multipass) -- follow the official setup docs; snapcraft auto-detects
  and manages the build environment.

## Build

From the repo root:

```sh
snapcraft pack
```

This pulls the `tailcat` source, builds it, and packs
`tailcat_<version>_amd64.snap` in the current directory.

## Install

```sh
sudo snap install ./tailcat_*.snap --dangerous
```

Check the snap's interface connections (should show `home`, `network`,
and `network-bind` auto-connected under strict confinement):

```sh
snap connections tailcat
```

## Run the tests

Once `tailcat` is installed (per above), run the full smoke-test suite:

```sh
tests/run_all.sh
```

Or run a single test script directly, e.g.:

```sh
tests/test_ssh.sh
```

Each script prints a `PASS`/`FAIL` line per check and a per-script
summary; `run_all.sh` prints an overall summary and exits non-zero if
any script fails. The tests are integration/smoke tests against the
real, installed snap -- they exercise real Tailscale DERP relay
infrastructure over the network (see [`docs/available_features.md`](docs/available_features.md)
and [`docs/known_issues.md`](docs/known_issues.md) for what they cover
and any known caveats).
