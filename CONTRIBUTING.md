# Contributing

## Prerequisites

- [snapcraft](https://snapcraft.io/docs/snapcraft-overview) -- follow
  the official install instructions for your platform.
- [LXD](https://documentation.ubuntu.com/lxd/en/latest/installing/),
  initialized (`lxd init`) -- used both as snapcraft's build provider
  and, separately, to run the two-container functional test suite (see
  below). Your user needs to be in the `lxd` group.
- [uv](https://docs.astral.sh/uv/) -- used to manage the Python
  environment for the test suite (e.g. `sudo snap install astral-uv
  --classic`, which provides the `uv` command).
- [just](https://just.systems/) (optional) -- a convenience wrapper
  around the build/lint/test commands below (e.g. `sudo snap install
  just --classic`). Every `just` recipe has an equivalent raw command
  documented alongside it, so it isn't required.

## Build

From the repo root:

```sh
snapcraft pack
# or: just build
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

The test suite is a [pytest](https://docs.pytest.org/) project under
[`tests/`](tests/), managed with `uv`. Unlike a typical snap smoke
test, it does **not** test against a snap installed on your local
machine -- instead, each test run spins up two fresh, disposable LXD
containers (`tailcat-server` and `tailcat-client`), installs the
locally-built `.snap` in both, and drives real client/server traffic
between them over Tailscale's live DERP relay infrastructure. Using
two separate containers (rather than two processes on one host) gives
"client" and "server" genuinely separate network namespaces --
necessary because two tailcat processes sharing a single host/NAT'd IP
were observed to reliably fail to reach each other (a same-host NAT
hairpinning limitation, not a bug in tailcat or this packaging).

```sh
cd tests
uv run pytest functional/
# or, from the repo root: just test
```

This will build `tailcat_<version>_amd64.snap` first (via `snapcraft
pack`) if one isn't already present in the repo root, then provision
both containers once per test session, and tear them down afterwards
(even on failure).

Run a single test file directly, e.g.:

```sh
uv run pytest functional/test_ssh.py
```

The tests exercise real Tailscale DERP relay infrastructure over the
network -- see [`docs/available_features.md`](docs/available_features.md)
and [`docs/known_issues.md`](docs/known_issues.md) for what they cover
and any known caveats.

## Lint / format

The test suite is linted and formatted with
[ruff](https://docs.astral.sh/ruff/), configured in
[`tests/pyproject.toml`](tests/pyproject.toml):

```sh
cd tests
uv run ruff check .    # or, from the repo root: just lint
uv run ruff format .   # or, from the repo root: just format
```
