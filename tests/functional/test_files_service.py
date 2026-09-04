"""serve --files=<dir>[:ro|:rw|:wo+], ls, and cp (fetch/upload/recursive).
(Ported from test_files_service.sh)

Server container hosts the files; client container performs ls/cp.
"""

from __future__ import annotations

import time

import helpers


def test_files_ro(server, client, server_workdir, client_workdir):
    ro_dir = f"{server_workdir}/files_ro"
    helpers.lxc_exec(server, f"mkdir -p {ro_dir}", check=True)
    helpers.write_file(server, f"{ro_dir}/readme.txt", "readonly content\n")

    server_log = f"{server_workdir}/ro_server.log"
    helpers.run_bg(server, f"tailcat serve --files={ro_dir}:ro files", server_log)
    addr = helpers.wait_for_addr(server, server_log, timeout=10)
    assert addr, ":ro setup: server never printed an address"
    assert helpers.wait_until_ready(client, addr), (
        "server never became ready to accept connections"
    )

    out = helpers.lxc_exec_retry(client, f"timeout 15 tailcat ls {addr}", timeout=20).output
    assert "readme.txt" in out, "ls does not list the read-only served file"

    helpers.settle()
    fetched = f"{client_workdir}/fetched_readme.txt"
    helpers.lxc_exec_retry(
        client, f"timeout 15 tailcat cp {addr}:readme.txt {fetched}", timeout=20
    )
    assert helpers.file_exists(client, fetched), "cp did not fetch a file from the :ro server"
    content = helpers.read_file(client, fetched)
    assert content == "readonly content\n", "fetched file content does not match"

    helpers.settle()
    hack_file = f"{client_workdir}/hack.txt"
    helpers.write_file(client, hack_file, "should not be writable\n")
    result = helpers.lxc_exec(client, f"timeout 15 tailcat cp {hack_file} {addr}:", timeout=20)
    assert result.returncode != 0, ":ro server unexpectedly accepted an upload"


def test_files_rw(server, client, server_workdir, client_workdir):
    rw_dir = f"{server_workdir}/files_rw"
    helpers.lxc_exec(server, f"mkdir -p {rw_dir}", check=True)

    server_log = f"{server_workdir}/rw_server.log"
    helpers.run_bg(server, f"tailcat serve --files={rw_dir}:rw files", server_log)
    addr = helpers.wait_for_addr(server, server_log, timeout=10)
    assert addr, ":rw setup: server never printed an address"
    assert helpers.wait_until_ready(client, addr), (
        "server never became ready to accept connections"
    )

    upload_file = f"{client_workdir}/rw_upload.txt"
    helpers.write_file(client, upload_file, f"rw upload {int(time.time())}\n")
    result = helpers.lxc_exec_retry(
        client, f"timeout 15 tailcat cp {upload_file} {addr}:", timeout=20
    )
    assert result.returncode == 0, ":rw server did not accept an upload"

    assert helpers.file_exists(server, f"{rw_dir}/rw_upload.txt"), (
        ":rw uploaded file does not exist with its original name"
    )
    helpers.settle()
    out = helpers.lxc_exec_retry(client, f"timeout 15 tailcat ls {addr}", timeout=20).output
    assert "rw_upload.txt" in out, ":rw server's ls does not see the uploaded file"


def test_files_wo_recursive(server, client, server_workdir, client_workdir):
    wop_dir = f"{server_workdir}/files_wop"
    photos_dir = f"{client_workdir}/photos"
    helpers.lxc_exec(server, f"mkdir -p {wop_dir}", check=True)
    helpers.lxc_exec(client, f"mkdir -p {photos_dir}/sub", check=True)
    helpers.write_file(client, f"{photos_dir}/a.txt", "photo1\n")
    helpers.write_file(client, f"{photos_dir}/sub/b.txt", "photo2\n")

    server_log = f"{server_workdir}/wop_server.log"
    helpers.run_bg(server, f"tailcat serve --files={wop_dir}:wo+ files", server_log)
    addr = helpers.wait_for_addr(server, server_log, timeout=10)
    assert addr, ":wo+ setup: server never printed an address"
    assert helpers.wait_until_ready(client, addr), (
        "server never became ready to accept connections"
    )

    result = helpers.lxc_exec_retry(
        client, f"timeout 15 tailcat cp -r {photos_dir} {addr}:photos", timeout=20
    )
    assert result.returncode == 0, (
        ":wo+ server did not accept a recursive directory upload (cp -r)"
    )

    assert helpers.file_exists(server, f"{wop_dir}/photos/a.txt"), (
        ":wo+ top-level file did not land with its original name"
    )
    assert helpers.file_exists(server, f"{wop_dir}/photos/sub/b.txt"), (
        ":wo+ nested file did not land with its original name"
    )

    helpers.settle()
    result = helpers.lxc_exec(client, f"timeout 15 tailcat ls {addr}", timeout=20)
    assert result.returncode != 0, ":wo+ server unexpectedly allowed listing"
