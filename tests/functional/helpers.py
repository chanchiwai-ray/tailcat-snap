"""Shared helpers for the functional/*.py tests.

These tests exercise a real, already-installed `tailcat` snap running in two
separate LXD containers (see conftest.py), talking to each other over real
Tailscale DERP relay infrastructure. Nothing here talks to the host's own
network stack directly for the tailcat protocol itself -- all `tailcat`
invocations happen *inside* a container via `lxc exec`, so that "client" and
"server" are genuinely different machines/network-namespaces, not just two
processes on the same loopback interface.
"""

from __future__ import annotations

import re
import shlex
import subprocess
import time
from dataclasses import dataclass

from tenacity import (
    Retrying,
    retry_if_exception_type,
    stop_after_attempt,
    stop_after_delay,
    wait_exponential,
    wait_fixed,
)


class CommandError(RuntimeError):
    """Raised by lxc_exec(..., check=True) on a non-zero exit code."""


# A short pause recommended between successive client<->server tailcat
# interactions within the same test (e.g. between a `cp` and a follow-up
# `ls`, or between successive `ssh` calls). wait_until_ready()/
# lxc_exec_retry() handle the "is it ready / is this dial transiently
# slow" cases with real polling+backoff, but a small fixed pause between
# distinct steps additionally reduces how often those retries are needed
# in the first place, since each fresh dial is a brand new DERP-relayed
# handshake over the real internet.
INTER_STEP_DELAY = 5


def settle() -> None:
    """Sleep INTER_STEP_DELAY seconds. Call between successive
    client<->server tailcat interactions within a test (see
    INTER_STEP_DELAY)."""
    time.sleep(INTER_STEP_DELAY)


class _NotDoneYet(Exception):
    """Internal signal used to drive tenacity retry loops below -- means
    "condition not met yet, keep polling", not a real error."""


class _PermanentFailure(Exception):
    """Internal signal used to drive tenacity retry loops below -- means
    "this isn't going to fix itself by waiting longer, stop polling now"."""


@dataclass
class Result:
    returncode: int
    stdout: str
    stderr: str

    @property
    def output(self) -> str:
        """Combined stdout+stderr, handy for assert_contains-style checks."""
        return self.stdout + self.stderr


def run(cmd: list[str], timeout: float | None = None) -> Result:
    """Run a command on the *host* (e.g. `lxc` itself). Never raises on
    non-zero exit -- callers check .returncode / .output explicitly."""
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return Result(proc.returncode, proc.stdout, proc.stderr)
    except subprocess.TimeoutExpired as e:
        stdout = e.stdout.decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
        stderr = e.stderr.decode() if isinstance(e.stderr, bytes) else (e.stderr or "")
        return Result(124, stdout, stderr + "\n[helpers.run: timed out]")


def lxc_exec(container: str, cmd: str, timeout: float | None = 30, check: bool = False) -> Result:
    """Run `cmd` (a shell snippet) inside `container` via `lxc exec` and wait
    for it to finish. For long-running/background processes use run_bg()
    instead -- this function blocks until `cmd` itself exits."""
    result = run(["lxc", "exec", container, "--", "bash", "-c", cmd], timeout=timeout)
    if check and result.returncode != 0:
        raise CommandError(
            f"lxc exec {container} -- bash -c {cmd!r} failed "
            f"(exit {result.returncode}): {result.output}"
        )
    return result


def run_bg(container: str, cmd: str, logfile: str, env: dict[str, str] | None = None) -> None:
    """Start `cmd` inside `container` in the background, redirecting its
    combined stdout+stderr to `logfile` (a path inside the container), and
    return immediately (mirrors the bash tests' `... &`/`disown` pattern).

    IMPORTANT: this pipes the tracked process's output through `tee` rather
    than a plain shell `>` redirect. Under strict-confinement snaps running
    inside an *unprivileged* LXD container, `snap-confine`'s own AppArmor
    profile denies "file_inherit" for a write fd pointing at a regular file
    (confirmed via `dmesg`/`journalctl -k`: `apparmor="DENIED"
    operation="file_inherit" profile="/usr/lib/snapd/snap-confine" ...
    requested_mask="w"`) -- so a direct `tailcat ... > logfile` redirect
    silently produces an empty logfile (the process still runs and exits
    0, it just never manages to write anything). Piping through `tee`
    instead means the confined process's own stdout fd is a *pipe* (which
    snap-confine's file_inherit policy does allow), while the actual
    regular-file open() is done by the unconfined `tee` process.
    """
    env_prefix = ""
    if env:
        env_prefix = " ".join(f"{k}={shlex.quote(v)}" for k, v in env.items()) + " "
    inner = f"{env_prefix}{cmd} 2>&1 | tee {shlex.quote(logfile)} > /dev/null"
    script = (
        f"rm -f {shlex.quote(logfile)}; "
        f"setsid bash -c {shlex.quote(inner)} < /dev/null > /dev/null 2>&1 & disown"
    )
    lxc_exec(container, script, timeout=15)


def wait_for_cloudinit(container: str, timeout: float = 180, interval: float = 2) -> bool:
    """Poll `cloud-init status` inside the container until it reports
    "status: done" (or timeout). `lxc exec ... cloud-init status --wait`
    doesn't block the way it would over a real ssh/console session (lxc exec
    returns before cloud-init is actually finished), so we poll instead."""

    def _check() -> bool:
        result = lxc_exec(container, "cloud-init status", timeout=15)
        if "status: done" in result.output:
            return True
        if "status: error" in result.output:
            raise _PermanentFailure("cloud-init reported status: error")
        raise _NotDoneYet()

    try:
        for attempt in Retrying(
            stop=stop_after_delay(timeout),
            wait=wait_fixed(interval),
            retry=retry_if_exception_type(_NotDoneYet),
            reraise=True,
        ):
            with attempt:
                return _check()
    except (_NotDoneYet, _PermanentFailure):
        return False
    return False  # pragma: no cover -- Retrying always either returns or raises above


def wait_for_addr(
    container: str, logfile: str, timeout: float = 15, interval: float = 0.5
) -> str | None:
    """Poll `logfile` inside `container` until a tco... tailcat address
    appears, or timeout. Returns the address, or None.

    Note: the returned address being printed does NOT mean the server is
    actually ready to accept incoming connections yet -- see
    wait_until_ready() below, which callers should use afterwards before
    connecting to it."""
    return wait_for_pattern(
        container, logfile, r"(tco[A-Za-z0-9_-]+)", timeout=timeout, interval=interval
    )


def wait_for_pattern(
    container: str,
    logfile: str,
    pattern: str,
    timeout: float = 15,
    interval: float = 0.5,
) -> str | None:
    """Poll `logfile` inside `container` until `pattern` (a Python regex,
    with a single capture group for the part to return -- or no group, in
    which case the whole match is returned) matches, or timeout."""
    regex = re.compile(pattern)

    def _check() -> str:
        result = lxc_exec(container, f"cat {shlex.quote(logfile)}", timeout=10)
        match = regex.search(result.stdout)
        if not match:
            raise _NotDoneYet()
        return match.group(1) if match.groups() else match.group(0)

    try:
        for attempt in Retrying(
            stop=stop_after_delay(timeout),
            wait=wait_fixed(interval),
            retry=retry_if_exception_type(_NotDoneYet),
            reraise=True,
        ):
            with attempt:
                return _check()
    except _NotDoneYet:
        return None
    return None  # pragma: no cover -- Retrying always either returns or raises above


def wait_until_ready(
    client: str,
    addr: str,
    initial: float = 3,
    max_wait: float = 10,
    attempts: int = 5,
    key: str | None = None,
) -> bool:
    """Confirms a tailcat server at `addr` is actually ready to accept
    incoming connections, by retrying a throwaway `tailcat ping` from
    `client`. Pass `key=<name>` for servers restricted with `--allow=...`,
    so the readiness ping itself uses an allowed client identity instead
    of the client container's default (unlisted) one.

    A tailcat server prints its tco... address as soon as it's registered
    with the DERP relay, but isn't actually ready to accept incoming
    connections (direct/DERP-relayed peer handshake) for a brief moment
    after that -- empirically, pinging immediately (0-2s after the
    address appears) reliably fails with "context deadline exceeded",
    while waiting >=3s reliably succeeds. Rather than a single blind
    sleep, this retries with exponential backoff starting at that
    confirmed-safe 3s, so it self-heals if a given run happens to need a
    bit longer (slow DERP handshake, etc.) instead of just failing.
    """
    key_flag = f"--key={key} " if key else ""

    def _check() -> bool:
        result = lxc_exec(client, f"timeout 10 tailcat {key_flag}ping {addr}", timeout=15)
        if "pong in" not in result.output:
            raise _NotDoneYet()
        return True

    try:
        for attempt in Retrying(
            stop=stop_after_attempt(attempts),
            wait=wait_exponential(multiplier=1, min=initial, max=max_wait),
            retry=retry_if_exception_type(_NotDoneYet),
            reraise=True,
        ):
            with attempt:
                return _check()
    except _NotDoneYet:
        return False
    return False  # pragma: no cover -- Retrying always either returns or raises above


# Substrings tailcat prints when a connection attempt (dial, ping, or an
# established session doing its own handshake) doesn't complete within its
# own internal timeout -- distinct from wait_until_ready()'s initial
# "is the server up at all" gate above. Even after a server is confirmed
# ready, *individual* later connections can still occasionally hit one of
# these transiently, since each is a fresh DERP-relayed/WireGuard
# handshake over the real internet.
TRANSIENT_ERROR_MARKERS = ("context deadline exceeded",)


def _looks_transient(result: Result) -> bool:
    return result.returncode != 0 and any(
        marker in result.output for marker in TRANSIENT_ERROR_MARKERS
    )


def lxc_exec_retry(
    container: str,
    cmd: str,
    timeout: float | None = 30,
    attempts: int = 6,
    initial: float = 3,
    max_wait: float = 15,
) -> Result:
    """Like lxc_exec(), but retries the whole command if it fails with one
    of TRANSIENT_ERROR_MARKERS (e.g. "context deadline exceeded" from a
    slow DERP handshake) -- inherent to driving real Tailscale DERP relay
    infrastructure over the real internet, not indicative of a real bug.
    Returns the last Result either way (a "real"/non-transient failure is
    returned immediately on the first attempt; a still-transient-looking
    failure after all retries are exhausted is returned as-is, so the
    caller's own assertion message stays meaningful instead of a generic
    retry error)."""
    last_result = Result(1, "", "lxc_exec_retry: never attempted")

    def _check() -> Result:
        nonlocal last_result
        last_result = lxc_exec(container, cmd, timeout=timeout)
        if _looks_transient(last_result):
            raise _NotDoneYet()
        return last_result

    try:
        for attempt in Retrying(
            stop=stop_after_attempt(attempts),
            wait=wait_exponential(multiplier=1, min=initial, max=max_wait),
            retry=retry_if_exception_type(_NotDoneYet),
            reraise=True,
        ):
            with attempt:
                return _check()
    except _NotDoneYet:
        return last_result
    return last_result  # pragma: no cover -- Retrying always either returns or raises above


def wait_for_file_nonempty(
    container: str,
    path: str,
    timeout: float = 15,
    interval: float = 0.5,
) -> str | None:
    """Poll for `path` inside `container` to exist and be non-empty (e.g. a
    file a background process writes once it's actually ready), or
    timeout. Returns its stripped contents, or None."""

    def _check() -> str:
        result = lxc_exec(container, f"cat {shlex.quote(path)} 2>/dev/null", timeout=10)
        content = result.stdout.strip()
        if not content:
            raise _NotDoneYet()
        return content

    try:
        for attempt in Retrying(
            stop=stop_after_delay(timeout),
            wait=wait_fixed(interval),
            retry=retry_if_exception_type(_NotDoneYet),
            reraise=True,
        ):
            with attempt:
                return _check()
    except _NotDoneYet:
        return None
    return None  # pragma: no cover -- Retrying always either returns or raises above


def pkill_tailcat(container: str) -> None:
    lxc_exec(container, "pkill tailcat >/dev/null 2>&1 || true", timeout=15)


def pkill_pattern(container: str, pattern: str) -> None:
    lxc_exec(container, f"pkill -f {shlex.quote(pattern)} >/dev/null 2>&1 || true", timeout=15)


def home_dir(container: str) -> str:
    return lxc_exec(container, "echo -n $HOME", timeout=10, check=True).stdout


def make_workdir(container: str, prefix: str = "tailcat-test") -> str:
    """Create a unique workdir directly under the container's real $HOME
    (tailcat's `home` plug only grants access under $HOME, excluding
    top-level dotfiles/dirs -- so workdirs must live under $HOME with a
    non-dot name, matching the constraint the original bash tests documented
    in lib.sh)."""
    result = lxc_exec(container, f"mktemp -d $HOME/{prefix}.XXXXXX", timeout=10, check=True)
    return result.stdout.strip()


def remove_path(container: str, path: str) -> None:
    lxc_exec(container, f"rm -rf {shlex.quote(path)}", timeout=15)


def file_exists(container: str, path: str) -> bool:
    return lxc_exec(container, f"test -f {shlex.quote(path)}", timeout=10).returncode == 0


def dir_exists(container: str, path: str) -> bool:
    return lxc_exec(container, f"test -d {shlex.quote(path)}", timeout=10).returncode == 0


def read_file(container: str, path: str) -> str | None:
    result = lxc_exec(container, f"cat {shlex.quote(path)}", timeout=10)
    if result.returncode != 0:
        return None
    return result.stdout


def write_file(container: str, path: str, content: str) -> None:
    lxc_exec(
        container,
        f"printf '%s' {shlex.quote(content)} > {shlex.quote(path)}",
        timeout=10,
        check=True,
    )


def count_files(container: str, dir_path: str) -> int:
    result = lxc_exec(
        container, f"find {shlex.quote(dir_path)} -type f 2>/dev/null | wc -l", timeout=10
    )
    try:
        return int(result.stdout.strip())
    except ValueError:
        return 0
