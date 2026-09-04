"""Session-level fixtures: launch two LXD containers ("tailcat-server" and
"tailcat-client"), install the locally-built tailcat snap in each, and tear
them down at the end of the test session.

Using two separate LXD containers (rather than two processes on the same
host) means "client" and "server" have genuinely separate network
namespaces/interfaces -- this was a deliberate choice after observing that
two tailcat processes sharing a single host/NAT'd IP reliably failed to
reach each other (see the project history / PR discussion), which looked
like a same-host NAT hairpinning limitation rather than a bug in tailcat or
in the snap packaging.
"""

from __future__ import annotations

import glob
import os
import time

import helpers
import pytest

PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
SNAP_CONTAINER_PATH = "/root/tailcat.snap"

SERVER = "tailcat-server"
CLIENT = "tailcat-client"
ALL_CONTAINERS = [SERVER, CLIENT]


def _find_or_build_snap() -> str:
    candidates = sorted(glob.glob(os.path.join(PROJECT_ROOT, "tailcat_*_amd64.snap")))
    if candidates:
        return candidates[-1]
    # Fall back to building it, matching `CONTRIBUTING.md`'s `snapcraft pack`.
    result = helpers.run(["snapcraft", "pack"], timeout=1800)
    if result.returncode != 0:
        raise RuntimeError(f"snapcraft pack failed: {result.output}")
    candidates = sorted(glob.glob(os.path.join(PROJECT_ROOT, "tailcat_*_amd64.snap")))
    if not candidates:
        raise RuntimeError("snapcraft pack finished but no tailcat_*_amd64.snap was produced")
    return candidates[-1]


def _container_exists(name: str) -> bool:
    result = helpers.run(["lxc", "list", name, "--format", "csv", "-c", "n"], timeout=15)
    return name in result.stdout.splitlines()


def _delete_container(name: str) -> None:
    helpers.run(["lxc", "delete", "--force", name], timeout=60)


def _launch_container(name: str) -> None:
    if _container_exists(name):
        _delete_container(name)
    result = helpers.run(["lxc", "launch", "ubuntu:24.04", name], timeout=120)
    if result.returncode != 0:
        raise RuntimeError(f"lxc launch {name} failed: {result.output}")


def _wait_for_network(name: str, timeout: float = 60) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = helpers.lxc_exec(name, "getent hosts tailscale.com", timeout=10)
        if result.returncode == 0:
            return
        time.sleep(2)
    raise RuntimeError(f"{name}: never got working DNS/network within {timeout}s")


def _wait_for_snapd(name: str, timeout: float = 60) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = helpers.lxc_exec(name, "snap version", timeout=10)
        if result.returncode == 0:
            return
        time.sleep(2)
    raise RuntimeError(f"{name}: snapd never became ready within {timeout}s")


def _provision_container(name: str, snap_path: str) -> None:
    _launch_container(name)
    if not helpers.wait_for_cloudinit(name, timeout=180):
        raise RuntimeError(f"{name}: cloud-init never reached 'status: done'")
    _wait_for_network(name)
    _wait_for_snapd(name)

    push = helpers.run(
        ["lxc", "file", "push", snap_path, f"{name}{SNAP_CONTAINER_PATH}"], timeout=60
    )
    if push.returncode != 0:
        raise RuntimeError(f"lxc file push to {name} failed: {push.output}")

    install = helpers.lxc_exec(
        name, f"snap install --dangerous {SNAP_CONTAINER_PATH}", timeout=120
    )
    if install.returncode != 0:
        raise RuntimeError(f"snap install --dangerous on {name} failed: {install.output}")

    version = helpers.lxc_exec(name, "tailcat --version", timeout=15)
    if version.returncode != 0:
        raise RuntimeError(f"tailcat --version on {name} failed after install: {version.output}")


@pytest.fixture(scope="session")
def containers():
    """Provisions both containers once per test session; tears them down
    unconditionally afterwards, even if provisioning or tests fail."""
    snap_path = _find_or_build_snap()
    try:
        for name in ALL_CONTAINERS:
            _provision_container(name, snap_path)
        yield {"server": SERVER, "client": CLIENT}
    finally:
        for name in ALL_CONTAINERS:
            _delete_container(name)


@pytest.fixture(scope="session")
def server(containers):
    return containers["server"]


@pytest.fixture(scope="session")
def client(containers):
    return containers["client"]


@pytest.fixture(autouse=True)
def _clean_processes(containers):
    """Kill any leftover tailcat/http.server processes on both containers
    before and after each test, mirroring lib.sh's per-script cleanup trap."""

    def _cleanup():
        for name in containers.values():
            helpers.pkill_tailcat(name)
            helpers.pkill_pattern(name, "http.server")

    _cleanup()
    yield
    _cleanup()


@pytest.fixture
def server_workdir(server):
    workdir = helpers.make_workdir(server)
    yield workdir
    helpers.remove_path(server, workdir)


@pytest.fixture
def client_workdir(client):
    workdir = helpers.make_workdir(client)
    yield workdir
    helpers.remove_path(client, workdir)
