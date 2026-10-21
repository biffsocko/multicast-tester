"""Tests for multicast-sender.py and multicast-listen.py.

Both scripts do their work at import time and have hyphens in their names,
so they can't be imported. Instead these tests run them the way you do:
as programs, in a subprocess, and check exit codes and output. The
end-to-end tests send real multicast on this machine, which Linux loops
back locally, so no second server is needed. Linux only (the sender reads
/dev/zero), which matches GitHub's ubuntu runners.
"""

import contextlib
import pathlib
import socket
import subprocess
import sys
import threading
import time

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
SENDER = ROOT / "multicast-sender.py"
LISTENER = ROOT / "multicast-listen.py"

GROUP = "239.255.42.99"  # administratively scoped: never leaves the site


def run(script, *args, timeout=20):
    """Run a script to completion and return the CompletedProcess."""
    return subprocess.run(
        [sys.executable, str(script), *map(str, args)],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,  # nonzero exits are what several tests are checking for
    )


@pytest.fixture
def local_ip():
    """IP of the interface holding the default route.

    connect() on a UDP socket sends nothing; it just asks the kernel which
    local address it would use. Multicast with no explicit interface goes
    out that same interface, so that's the one to join on.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try:
            s.connect(("192.0.2.1", 9))  # TEST-NET-1: documentation-only address
        except OSError:
            pytest.skip("no default route on this machine")
        return s.getsockname()[0]


@pytest.fixture
def port():
    """A UDP port nothing else is using, so parallel runs don't collide."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


@pytest.fixture
def sender(port):
    """Run multicast-sender.py in the background for the length of a test."""
    # -u: unbuffered stdout. Piped (not a terminal), Python buffers output in
    # 8 KB blocks, so "Now sending data" would sit in the buffer forever and
    # readline() below would hang.
    proc = subprocess.Popen(
        [sys.executable, "-u", str(SENDER), GROUP, str(port)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    yield proc
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


@contextlib.contextmanager
def receiver(port, if_ip, timeout=5):
    """A multicast socket joined to GROUP on if_ip (a stand-in listener)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((GROUP, port))
    s.setsockopt(
        socket.IPPROTO_IP,
        socket.IP_ADD_MEMBERSHIP,
        socket.inet_aton(GROUP) + socket.inet_aton(if_ip),
    )
    s.settimeout(timeout)
    try:
        yield s
    finally:
        s.close()


@contextlib.contextmanager
def background_sender(port, if_ip, payload=b"\xab" * 64):
    """Send payload to GROUP:port repeatedly from a thread (a stand-in sender)."""
    stop = threading.Event()
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 1)
    s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(if_ip))

    def loop():
        while not stop.is_set():
            s.sendto(payload, (GROUP, port))
            time.sleep(0.05)

    t = threading.Thread(target=loop, daemon=True)
    t.start()
    try:
        yield payload
    finally:
        stop.set()
        t.join()
        s.close()


# --- multicast-sender.py: command line -------------------------------------


def test_sender_help():
    r = run(SENDER, "--help")
    assert r.returncode == 0
    assert "group" in r.stdout and "port" in r.stdout


@pytest.mark.parametrize("args", [[], [GROUP]], ids=["no-args", "group-only"])
def test_sender_missing_args(args):
    r = run(SENDER, *args)
    assert r.returncode == 2  # argparse's usage-error exit code
    assert "usage:" in r.stderr


def test_sender_rejects_non_integer_port():
    r = run(SENDER, GROUP, "abc")
    assert r.returncode == 2
    assert "invalid int value" in r.stderr


def test_sender_fails_on_out_of_range_port():
    r = run(SENDER, GROUP, 70000)
    assert r.returncode != 0


# --- multicast-sender.py: on the wire --------------------------------------


def test_sender_announces_itself(sender):
    line = sender.stdout.readline()
    assert line.strip() == "Now sending data"


def test_sender_sends_1024_zero_bytes(sender, port, local_ip):
    with receiver(port, local_ip) as r:
        data = r.recv(65535)
    assert data == b"\x00" * 1024


# --- multicast-listen.py: command line -------------------------------------


@pytest.mark.parametrize(
    "args",
    [[], [GROUP], [GROUP, 1234], [GROUP, 1234, "127.0.0.1", "extra"]],
    ids=["0-args", "1-arg", "2-args", "4-args"],
)
def test_listener_wrong_arg_count_prints_usage(args):
    r = run(LISTENER, *args)
    assert r.returncode == 1
    assert "[multicast group] [multicast port] [local interface ip address]" in r.stdout


def test_listener_rejects_non_integer_port():
    r = run(LISTENER, GROUP, "abc", "127.0.0.1")
    assert r.returncode != 0


def test_listener_rejects_garbage_group():
    r = run(LISTENER, "not-an-ip", 1234, "127.0.0.1")
    assert r.returncode != 0


# --- multicast-listen.py: on the wire --------------------------------------


def test_listener_receives_data(port, local_ip):
    with background_sender(port, local_ip) as payload:
        r = run(LISTENER, GROUP, port, local_ip)
    assert r.returncode == 0
    assert "printing first 10240 bytes" in r.stdout
    assert repr(payload) in r.stdout


def test_listener_reports_timeout(port, local_ip):
    """Nobody is sending, so the 10 s timeout fires. (Slowest test here.)"""
    r = run(LISTENER, GROUP, port, local_ip)
    assert f"failed reading group {GROUP} on port {port}" in r.stdout


def test_listener_timeout_exits_nonzero(port, local_ip):
    """A troubleshooting tool should fail loudly so scripts can check $?."""
    r = run(LISTENER, GROUP, port, local_ip)
    assert r.returncode == 1
    assert "Traceback" not in r.stderr

# --- both together: the README's two-server demo on one box ----------------


def test_end_to_end_sender_to_listener(sender, port, local_ip):
    r = run(LISTENER, GROUP, port, local_ip)
    assert r.returncode == 0
    assert "\\x00\\x00\\x00\\x00" in r.stdout
    assert "failed reading" not in r.stdout
