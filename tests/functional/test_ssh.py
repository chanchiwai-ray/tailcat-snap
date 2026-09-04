"""tailcat ssh: remote command execution, landing in the server's real
$HOME, and the coreutils-allowlist caveat (see docs/known_issues.md #3).
(Ported from test_ssh.sh)
"""

from __future__ import annotations

import helpers


def test_ssh_remote_exec(server, client, server_workdir):
    server_log = f"{server_workdir}/ssh_server.log"
    helpers.run_bg(server, "tailcat serve no-auth-ssh", server_log)
    addr = helpers.wait_for_addr(server, server_log, timeout=10)
    assert addr, "ssh setup: server never printed an address"
    assert helpers.wait_until_ready(client, addr), "server never became ready to accept connections"

    out = helpers.lxc_exec_retry(client, f"timeout 15 tailcat ssh {addr} 'pwd'", timeout=20).output
    assert out.strip() == helpers.home_dir(server), "ssh remote command did not run in the server's real $HOME"

    helpers.settle()
    out = helpers.lxc_exec_retry(client, f"timeout 15 tailcat ssh {addr} 'echo remote-exec-ok'", timeout=20).output
    assert "remote-exec-ok" in out, "ssh did not run an arbitrary remote command / return its output"

    helpers.settle()
    # Known caveat: only an allowlisted set of coreutils is exec-able inside
    # the confined server's shell session (see docs/known_issues.md #3).
    # whoami is a real-world example that's NOT on the allowlist.
    out = helpers.lxc_exec_retry(client, f"timeout 15 tailcat ssh {addr} whoami", timeout=20).output
    assert "permission denied" in out.lower(), (
        f"ssh: whoami unexpectedly succeeded -- has the confinement template's allowlist "
        f"changed? Update known_issues.md #3 and this test if so. Got: {out}"
    )
