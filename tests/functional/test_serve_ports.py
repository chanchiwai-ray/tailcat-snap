"""serve <port>, serve all, and a combined serve <port>,no-auth-ssh.
(Ported from test_serve_ports.sh)
"""

from __future__ import annotations

import helpers


def _http_body_ok(client: str, addr: str, port: int) -> str:
    """Sends a raw HTTP/1.0 GET through tailcat and returns the response's
    first line."""
    cmd = (
        f"printf 'GET / HTTP/1.0\\r\\nHost: local\\r\\n\\r\\n' | "
        f"timeout 15 tailcat {addr} {port} 2>/dev/null | head -1"
    )
    return helpers.lxc_exec_retry(client, cmd, timeout=20).stdout


def test_serve_port(server, client, server_workdir):
    helpers.run_bg(
        server, "python3 -m http.server 18080 --directory /tmp", f"{server_workdir}/http.log"
    )
    server_log = f"{server_workdir}/serve1.log"
    helpers.run_bg(server, "tailcat serve 18080", server_log)
    addr = helpers.wait_for_addr(server, server_log, timeout=10)
    assert addr, "serve <port>: server never printed an address"
    assert helpers.wait_until_ready(client, addr), (
        "server never became ready to accept connections"
    )

    helpers.settle()
    resp = _http_body_ok(client, addr, 18080)
    assert "200 OK" in resp, "serve <port> did not forward to the local HTTP server"


def test_serve_all(server, client, server_workdir):
    helpers.run_bg(
        server, "python3 -m http.server 18081 --directory /tmp", f"{server_workdir}/http.log"
    )
    server_log = f"{server_workdir}/serve2.log"
    helpers.run_bg(server, "tailcat serve all", server_log)
    addr = helpers.wait_for_addr(server, server_log, timeout=10)
    assert addr, "serve all: server never printed an address"
    assert helpers.wait_until_ready(client, addr), (
        "server never became ready to accept connections"
    )

    helpers.settle()
    resp = _http_body_ok(client, addr, 18081)
    assert "200 OK" in resp, "serve all did not forward to a port not explicitly named"


def test_serve_combined_port_and_no_auth_ssh(server, client, server_workdir):
    helpers.run_bg(
        server, "python3 -m http.server 18082 --directory /tmp", f"{server_workdir}/http.log"
    )
    server_log = f"{server_workdir}/serve3.log"
    helpers.run_bg(server, "tailcat serve 18082,no-auth-ssh", server_log)
    addr = helpers.wait_for_addr(server, server_log, timeout=10)
    assert addr, "combined serve: server never printed an address"
    assert helpers.wait_until_ready(client, addr), (
        "server never became ready to accept connections"
    )

    helpers.settle()
    resp = _http_body_ok(client, addr, 18082)
    assert "200 OK" in resp, "combined serve: port forwarding does not work"

    helpers.settle()
    ssh_out = helpers.lxc_exec_retry(
        client, f"timeout 15 tailcat ssh {addr} 'echo combo-ssh-ok'", timeout=20
    ).output
    assert "combo-ssh-ok" in ssh_out, (
        "combined serve: no-auth-ssh does not work in the same server"
    )
