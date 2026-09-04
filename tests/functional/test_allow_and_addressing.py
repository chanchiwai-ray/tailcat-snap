"""--allow (client allowlisting) and --full-address.
(Ported from test_allow_and_addressing.sh)
"""

from __future__ import annotations

import time

import helpers
import pytest

CLIENT_KEY = "tc_test_allow_client"


def _extract_nodekey(output: str) -> str | None:
    for line in output.splitlines():
        line = line.strip()
        if line.startswith("nodekey:"):
            return line
    return None


@pytest.fixture(autouse=True)
def _cleanup_key(client):
    yield
    helpers.lxc_exec(client, f"tailcat genkey --delete --key={CLIENT_KEY}", timeout=10)


def test_allow_permits_the_allowed_client(server, client, server_workdir, client_workdir):
    out = helpers.lxc_exec(
        client, f"tailcat genkey --client --key={CLIENT_KEY} --force", timeout=15
    ).output
    client_pub = _extract_nodekey(out)
    assert client_pub, f"couldn't generate a client key, got: {out!r}"

    server_log = f"{server_workdir}/allow_server.log"
    helpers.run_bg(server, f"tailcat serve --allow={client_pub}", server_log)
    addr = helpers.wait_for_addr(server, server_log, timeout=10)
    assert addr, "--allow setup: server never printed an address"
    assert helpers.wait_until_ready(client, addr, key=CLIENT_KEY), (
        "server never became ready to accept connections"
    )

    msg = f"allowed client {int(time.time())}"
    helpers.settle()
    result = helpers.lxc_exec_retry(
        client, f"echo {msg!r} | timeout 15 tailcat --key={CLIENT_KEY} {addr}", timeout=20
    )
    assert result.returncode == 0, "the allowed client's connection did not succeed"

    time.sleep(1)
    server_log_contents = helpers.read_file(server, server_log) or ""
    assert msg in server_log_contents, "the allowed client's message never reached the server"


def test_allow_rejects_an_unlisted_client(server, client, server_workdir):
    out = helpers.lxc_exec(
        client, f"tailcat genkey --client --key={CLIENT_KEY} --force", timeout=15
    ).output
    client_pub = _extract_nodekey(out)
    assert client_pub, f"couldn't generate a client key, got: {out!r}"

    server_log = f"{server_workdir}/allow_server2.log"
    helpers.run_bg(server, f"tailcat serve --allow={client_pub}", server_log)
    addr = helpers.wait_for_addr(server, server_log, timeout=10)
    assert addr, "--allow disallowed-client setup: server never printed an address"
    assert helpers.wait_until_ready(client, addr, key=CLIENT_KEY), (
        "server never became ready to accept connections"
    )

    # A different (unlisted, ephemeral) client key should be rejected.
    helpers.settle()
    result = helpers.lxc_exec(
        client, f"echo 'disallowed client' | timeout 8 tailcat --key=new {addr}", timeout=15
    )
    assert result.returncode != 0, "an unlisted client was unexpectedly allowed through"


def test_full_address_is_longer_than_short_address(server, server_workdir):
    short_log = f"{server_workdir}/short_server.log"
    helpers.run_bg(server, "tailcat", short_log)
    short_addr = helpers.wait_for_addr(server, short_log, timeout=10)
    helpers.pkill_tailcat(server)
    time.sleep(1)

    full_log = f"{server_workdir}/fa_server.log"
    helpers.run_bg(server, "tailcat serve --full-address", full_log)
    full_addr = helpers.wait_for_addr(server, full_log, timeout=10)

    assert short_addr and full_addr, "a server never printed an address"
    assert len(full_addr) > len(short_addr), (
        "--full-address: printed address is not longer than a short address"
    )
