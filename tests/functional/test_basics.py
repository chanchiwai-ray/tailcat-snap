"""Basic invocation subcommands that need no peer: --help, version,
printpub, parse, resolve, readme. (Ported from test_basics.sh)

Runs entirely on the "server" container -- these don't require a second
peer, just a running tailcat process to produce a real address to parse.
"""

from __future__ import annotations

import helpers


def test_help_prints_subcommands(server):
    out = helpers.lxc_exec(server, "tailcat --help", timeout=15).output
    assert "SUBCOMMANDS" in out


def test_version_flag_prints_version_string(server):
    out = helpers.lxc_exec(server, "tailcat --version", timeout=15).output
    assert "." in out


def test_version_subcommand_prints_version_string(server):
    out = helpers.lxc_exec(server, "tailcat version", timeout=15).output
    assert "." in out


def test_printpub_prints_nodekey(server):
    out = helpers.lxc_exec(server, "tailcat printpub", timeout=15).output
    assert "nodekey:" in out


def test_readme_prints_upstream_readme(server):
    out = helpers.lxc_exec(server, "tailcat readme", timeout=15).output
    assert "Tailcat" in out


def test_parse_and_resolve(server, server_workdir):
    logfile = f"{server_workdir}/server.log"
    helpers.run_bg(server, "tailcat", logfile)
    addr = helpers.wait_for_addr(server, logfile, timeout=10)
    assert addr, "server never printed an address"

    out = helpers.lxc_exec(server, f"tailcat parse {addr}", timeout=15).output
    assert "ServerPublic" in out
    assert "RegionID" in out

    out = helpers.lxc_exec(server, f"timeout 15 tailcat resolve {addr}", timeout=20).output
    assert "tco" in out
    # The resolved address should be longer (embeds DERP node info).
    assert len(out) > len(addr), "resolved address is not longer than the input"
