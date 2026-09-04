"""serve exit-node routing (via socks to the open internet, and via
ssh -p ip:port reaching the exit node's own sshd), plus the "socks" and
"forward" subcommands against a non-exit-node server.
(Ported from test_exit_node_and_proxying.sh)
"""

from __future__ import annotations

import helpers


def test_forward(server, client, server_workdir, client_workdir):
    helpers.run_bg(
        server, "python3 -m http.server 18091 --directory /tmp", f"{server_workdir}/http.log"
    )
    server_log = f"{server_workdir}/fwd_server.log"
    helpers.run_bg(server, "tailcat serve 18091", server_log)
    addr = helpers.wait_for_addr(server, server_log, timeout=10)
    assert addr, "forward: server never printed an address"
    assert helpers.wait_until_ready(client, addr), (
        "server never became ready to accept connections"
    )

    helpers.settle()
    # tailcat forward's docs only show <tc-addr> <port> (same local/remote)
    # or <tc-addr> <local:remote> with an explicit non-zero local port --
    # there's no "0:remote" ephemeral-local-port syntax (confirmed: it
    # errors with `mapping "0:18091" is invalid: local port: invalid port
    # "0"`), so we just pick a fixed local port ourselves instead of
    # trying to parse one back out of the command's output.
    local_port = 28091
    client_log = f"{client_workdir}/fwd_client.log"
    helpers.run_bg(client, f"tailcat forward {addr} {local_port}:18091", client_log)
    helpers.settle()

    code = helpers.lxc_exec_retry(
        client,
        f"curl -s -o /dev/null -w '%{{http_code}}' http://127.0.0.1:{local_port}/",
        timeout=15,
    ).stdout
    assert code == "200", "forward: local port does not reach the server's forwarded port"


def test_socks_non_exit_node(server, client, server_workdir, client_workdir):
    helpers.run_bg(
        server, "python3 -m http.server 18092 --directory /tmp", f"{server_workdir}/http.log"
    )
    server_log = f"{server_workdir}/socks_server.log"
    helpers.run_bg(server, "tailcat serve 18092", server_log)
    addr = helpers.wait_for_addr(server, server_log, timeout=10)
    assert addr, "socks: server never printed an address"
    assert helpers.wait_until_ready(client, addr), (
        "server never became ready to accept connections"
    )

    helpers.settle()
    client_log = f"{client_workdir}/socks_client.log"
    helpers.run_bg(client, f"tailcat socks {addr}", client_log)
    socks_port = helpers.wait_for_pattern(client, client_log, r"127\.0\.0\.1:(\d+)", timeout=15)
    assert socks_port, "socks: proxy never printed its listen port"

    code = helpers.lxc_exec_retry(
        client,
        f"curl -s --socks5-hostname 127.0.0.1:{socks_port} -o /dev/null -w '%{{http_code}}' "
        f"http://server.tailcat:18092/",
        timeout=15,
    ).stdout
    assert code == "200", "socks: server.tailcat magic hostname does not reach the server"

    helpers.settle()
    code2 = helpers.lxc_exec_retry(
        client,
        f"curl -s --socks5-hostname 127.0.0.1:{socks_port} -o /dev/null -w '%{{http_code}}' "
        f"http://{addr}:18092/",
        timeout=15,
    ).stdout
    assert code2 == "200", "socks: tc-addr used directly as hostname does not reach the server"


def test_exit_node_socks_routes_to_internet(server, client, server_workdir, client_workdir):
    server_log = f"{server_workdir}/exit_server.log"
    helpers.run_bg(server, "tailcat serve exit-node", server_log)
    addr = helpers.wait_for_addr(server, server_log, timeout=10)
    assert addr, "exit-node: server never printed an address"
    assert helpers.wait_until_ready(client, addr), (
        "server never became ready to accept connections"
    )

    helpers.settle()
    client_log = f"{client_workdir}/exit_socks.log"
    helpers.run_bg(client, f"tailcat socks {addr}", client_log)
    exit_port = helpers.wait_for_pattern(client, client_log, r"127\.0\.0\.1:(\d+)", timeout=15)
    assert exit_port, "exit-node socks: proxy never printed its listen port"

    code = helpers.lxc_exec_retry(
        client,
        f"curl -s --socks5-hostname 127.0.0.1:{exit_port} --max-time 15 -o /dev/null "
        f"-w '%{{http_code}}' https://example.com/",
        timeout=20,
    ).stdout
    assert code == "200", "exit-node: does not route real internet traffic through the exit node"


def test_exit_node_ssh_dash_p_reaches_real_sshd(server, client, server_workdir):
    server_log = f"{server_workdir}/exit_server2.log"
    helpers.run_bg(server, "tailcat serve exit-node", server_log)
    addr = helpers.wait_for_addr(server, server_log, timeout=10)
    assert addr, "exit-node ssh -p setup: server never printed an address"
    assert helpers.wait_until_ready(client, addr), (
        "server never became ready to accept connections"
    )

    helpers.settle()
    # This only proves the TCP route through the exit node works (we don't
    # have real host SSH credentials in this test environment); a genuine
    # "Permission denied (publickey)" from the real sshd confirms the
    # route, as opposed to a connection-level error.
    ssh_out = helpers.lxc_exec_retry(
        client, f"timeout 15 tailcat ssh -p 127.0.0.1:22 {addr} true", timeout=20
    ).output
    assert "Permission denied" in ssh_out or ssh_out.strip() == "", (
        f"exit-node ssh -p: unexpected response: {ssh_out}"
    )
