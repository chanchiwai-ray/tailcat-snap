"""Documents/verifies two confinement-caused failure modes rather than
successes, matching docs/known_issues.md:
  - cp's local-side path must be under $HOME (issue #3's note)
  - socks <addr> <cmd> can't exec external tools like curl (issue #6)
(Ported from test_known_limitations.sh)
"""

from __future__ import annotations

import helpers


def test_cp_local_path_outside_home_fails(server, client, server_workdir):
    rw_dir = f"{server_workdir}/files_rw2"
    helpers.lxc_exec(server, f"mkdir -p {rw_dir}", check=True)

    server_log = f"{server_workdir}/cp_server.log"
    helpers.run_bg(server, f"tailcat serve --files={rw_dir}:rw files", server_log)
    addr = helpers.wait_for_addr(server, server_log, timeout=10)
    assert addr, "cp-outside-home setup: server never printed an address"
    assert helpers.wait_until_ready(client, addr), (
        "server never became ready to accept connections"
    )

    helpers.write_file(client, "/tmp/tailcat_outside_home_test.txt", "should fail\n")
    helpers.settle()
    result = helpers.lxc_exec(
        client, f"timeout 15 tailcat cp /tmp/tailcat_outside_home_test.txt {addr}:", timeout=20
    )
    assert result.returncode != 0, (
        "cp: a local path under /tmp (outside $HOME) unexpectedly succeeded -- has the "
        "home-plug restriction changed? Update known_issues.md and this test if so."
    )
    helpers.lxc_exec(client, "rm -f /tmp/tailcat_outside_home_test.txt")


def test_socks_cmd_curl_not_visible_inside_confinement(server, client, server_workdir):
    server_log = f"{server_workdir}/socks_cmd_server.log"
    helpers.run_bg(server, "tailcat serve 18099", server_log)
    addr = helpers.wait_for_addr(server, server_log, timeout=10)
    assert addr, "socks <cmd> setup: server never printed an address"
    assert helpers.wait_until_ready(client, addr), (
        "server never became ready to accept connections"
    )

    out = helpers.lxc_exec_retry(
        client, f"timeout 15 tailcat socks {addr} curl -s http://server.tailcat:18099/", timeout=20
    ).output
    assert "executable file not found" in out.lower(), (
        f"socks <cmd> curl: unexpected result -- has curl been bundled or become visible? "
        f"Update known_issues.md #6 and this test if so. Got: {out}"
    )
