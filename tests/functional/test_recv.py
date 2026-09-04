"""recv (flat drop-box) and recv --accept-dirs (recursive drop-box).
(Ported from test_recv.sh)
"""

from __future__ import annotations

import time

import helpers


def test_recv_flat(server, client, server_workdir, client_workdir):
    inbox = f"{server_workdir}/inbox"
    helpers.lxc_exec(server, f"mkdir -p {inbox}", check=True)

    server_log = f"{server_workdir}/recv_server.log"
    helpers.run_bg(server, f"tailcat recv {inbox}", server_log)
    addr = helpers.wait_for_addr(server, server_log, timeout=10)
    assert addr, "recv setup: server never printed an address"
    assert helpers.wait_until_ready(client, addr), "server never became ready to accept connections"

    log_contents = helpers.read_file(server, server_log) or ""
    assert "write-only" in log_contents, "recv does not announce a write-only drop box"

    drop_file = f"{client_workdir}/drop.txt"
    helpers.write_file(client, drop_file, f"dropped file {int(time.time())}\n")
    helpers.settle()
    result = helpers.lxc_exec_retry(client, f"timeout 15 tailcat cp {drop_file} {addr}:", timeout=20)
    assert result.returncode == 0, "recv did not accept an upload"

    # Flat mode saves under a server-chosen unique name, not the original
    # filename -- so just check *some* file landed.
    assert helpers.count_files(server, inbox) >= 1, "no file appeared in the inbox directory"


def test_recv_accept_dirs(server, client, server_workdir, client_workdir):
    inbox_dirs = f"{server_workdir}/inbox_dirs"
    docs_dir = f"{client_workdir}/docs"
    helpers.lxc_exec(server, f"mkdir -p {inbox_dirs}", check=True)
    helpers.lxc_exec(client, f"mkdir -p {docs_dir}/sub", check=True)
    helpers.write_file(client, f"{docs_dir}/x.txt", "d1\n")
    helpers.write_file(client, f"{docs_dir}/sub/y.txt", "d2\n")

    server_log = f"{server_workdir}/recv_dirs_server.log"
    helpers.run_bg(server, f"tailcat recv --accept-dirs {inbox_dirs}", server_log)
    addr = helpers.wait_for_addr(server, server_log, timeout=10)
    assert addr, "recv --accept-dirs setup: server never printed an address"
    assert helpers.wait_until_ready(client, addr), "server never became ready to accept connections"

    result = helpers.lxc_exec_retry(client, f"timeout 15 tailcat cp -r {docs_dir} {addr}:docs", timeout=20)
    assert result.returncode == 0, "recv --accept-dirs did not accept a recursive upload"

    assert helpers.file_exists(server, f"{inbox_dirs}/docs/x.txt"), (
        "recv --accept-dirs: top-level file did not keep its name"
    )
    assert helpers.file_exists(server, f"{inbox_dirs}/docs/sub/y.txt"), (
        "recv --accept-dirs: nested file did not keep its name"
    )
