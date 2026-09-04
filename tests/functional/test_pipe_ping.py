"""Basic stdin/stdout pipe (default server mode) across two containers, ping,
--json, and the TAILCAT_ADDR_FILE environment variable (both plain-path and
tcp: modes). (Ported from test_pipe_ping.sh)
"""

from __future__ import annotations

import time

import helpers


def test_basic_pipe_round_trip(server, client, server_workdir, client_workdir):
    server_log = f"{server_workdir}/server.log"
    helpers.run_bg(server, "tailcat", server_log)
    addr = helpers.wait_for_addr(server, server_log, timeout=10)
    assert addr, "server never printed an address"
    assert helpers.wait_until_ready(client, addr), "server never became ready to accept connections"

    msg = f"hello from test_pipe_ping {int(time.time())}"
    helpers.settle()
    result = helpers.lxc_exec_retry(
        client, f"echo {msg!r} | timeout 20 tailcat {addr}", timeout=25
    )
    assert result.returncode == 0, "client did not exit 0 after sending its message"

    time.sleep(1)
    server_log_contents = helpers.read_file(server, server_log) or ""
    assert msg in server_log_contents, "server log does not contain the client's message"


def test_ping(server, client, server_workdir):
    server_log = f"{server_workdir}/server2.log"
    helpers.run_bg(server, "tailcat", server_log)
    addr = helpers.wait_for_addr(server, server_log, timeout=10)
    assert addr, "ping setup: server never printed an address"

    assert helpers.wait_until_ready(client, addr), "ping never received a pong"


def test_json_flag_writes_listen_addr(server, server_workdir):
    logfile = f"{server_workdir}/server_json.log"
    helpers.run_bg(server, "tailcat --json", logfile)
    found = helpers.wait_for_pattern(server, logfile, r'("listenAddr")', timeout=10)
    assert found, "server never wrote a JSON line containing listenAddr"


def test_addr_file_plain_path(server, server_workdir):
    addr_file = f"{server_workdir}/addr.txt"
    server_log = f"{server_workdir}/server3.log"
    helpers.run_bg(server, "tailcat", server_log, env={"TAILCAT_ADDR_FILE": addr_file})
    addr = helpers.wait_for_addr(server, server_log, timeout=10)
    assert addr

    assert helpers.file_exists(server, addr_file), "TAILCAT_ADDR_FILE did not write a file"
    written = (helpers.read_file(server, addr_file) or "").strip()
    assert written == addr


def test_addr_file_tcp_mode(server, server_workdir):
    recv_log = f"{server_workdir}/tcp_recv.log"
    port_file = f"{recv_log}.port"

    # Written to a file rather than piped in via a heredoc: run_bg() appends
    # "2>&1 | tee logfile" after whatever command it's given, and a shell
    # heredoc's closing delimiter must be alone on its own line -- appending
    # a pipeline right after it breaks the heredoc syntax.
    listener_py = f"""\
import socket, sys
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind(("127.0.0.1", 0))
port = s.getsockname()[1]
with open({port_file!r}, "w") as f:
    f.write(str(port))
s.listen(1)
conn, _ = s.accept()
data = conn.recv(4096)
with open({recv_log!r}, "w") as f:
    f.write(data.decode().strip())
conn.close()
"""
    listener_path = f"{server_workdir}/listener.py"
    helpers.write_file(server, listener_path, listener_py)
    helpers.run_bg(server, f"python3 {listener_path}", f"{server_workdir}/listener.log")

    tcp_port = helpers.wait_for_file_nonempty(server, port_file, timeout=15)
    assert tcp_port, "TAILCAT_ADDR_FILE tcp: listener never published its port"

    server_log = f"{server_workdir}/server4.log"
    helpers.run_bg(
        server,
        "tailcat",
        server_log,
        env={"TAILCAT_ADDR_FILE": f"tcp:127.0.0.1:{tcp_port}"},
    )
    addr = helpers.wait_for_addr(server, server_log, timeout=10)
    assert addr
    time.sleep(1)

    assert helpers.file_exists(server, recv_log), "TAILCAT_ADDR_FILE tcp: mode: listener never received anything"
    received = (helpers.read_file(server, recv_log) or "").strip()
    assert received == addr
