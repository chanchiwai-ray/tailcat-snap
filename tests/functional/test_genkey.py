"""genkey: basic generation, --list, --delete, --client, --region=list,
--region=<code>, --fixed-region, and the --embed-derp-map crash (see
docs/known_issues.md #5) plus its workaround. (Ported from test_genkey.sh)

Single-container -- genkey doesn't need a peer.
"""

from __future__ import annotations

import helpers
import pytest

KEYS = [
    "tc_test_basic",
    "tc_test_client",
    "tc_test_region",
    "tc_test_fixed",
    "tc_test_embed_ok",
    "tc_test_embed_bug",
]


@pytest.fixture(autouse=True)
def _cleanup_keys(server):
    yield
    for key in KEYS:
        helpers.lxc_exec(server, f"tailcat genkey --delete --key={key}", timeout=10)


def test_genkey_basic_list_delete(server):
    out = helpers.lxc_exec(server, "tailcat genkey --key=tc_test_basic --force", timeout=15).output
    assert "tco" in out

    out = helpers.lxc_exec(server, "tailcat genkey --list", timeout=15).output
    assert "tc_test_basic" in out

    helpers.lxc_exec(server, "tailcat genkey --delete --key=tc_test_basic", timeout=15)
    out = helpers.lxc_exec(server, "tailcat genkey --list", timeout=15).output
    assert "tc_test_basic" not in out


def test_genkey_client(server):
    out = helpers.lxc_exec(
        server, "tailcat genkey --client --key=tc_test_client --force", timeout=15
    ).output
    assert "nodekey:" in out


def test_genkey_region_list(server):
    out = helpers.lxc_exec(server, "timeout 15 tailcat genkey --region=list", timeout=20).output
    assert "fra" in out


def test_genkey_region_fra(server):
    out = helpers.lxc_exec(
        server, "timeout 15 tailcat genkey --key=tc_test_region --region=fra --force", timeout=20
    ).output
    assert "tco" in out


def test_genkey_fixed_region(server):
    out = helpers.lxc_exec(
        server, "timeout 15 tailcat genkey --key=tc_test_fixed --fixed-region --force", timeout=20
    ).output
    assert "tco" in out


def test_genkey_embed_derp_map_with_explicit_region_succeeds(server):
    out = helpers.lxc_exec(
        server,
        "timeout 15 tailcat genkey --key=tc_test_embed_ok --embed-derp-map --region=fra --force",
        timeout=20,
    ).output
    assert "tco" in out


def test_genkey_embed_derp_map_with_default_region_auto_fails(server):
    """Known upstream bug, see docs/known_issues.md #5. If this starts
    passing, the upstream bug has likely been fixed -- update
    known_issues.md and this test."""
    result = helpers.lxc_exec(
        server,
        "timeout 15 tailcat genkey --key=tc_test_embed_bug --embed-derp-map --force",
        timeout=20,
    )
    assert result.returncode != 0, (
        "genkey --embed-derp-map --region=auto (default) unexpectedly succeeded"
    )
