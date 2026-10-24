import os
import socket
import stat
from pathlib import Path

import pytest


def test_private_xdg_paths(tmp_path):
    for key in (
        "HOME",
        "XDG_DATA_HOME",
        "XDG_CONFIG_HOME",
        "XDG_CACHE_HOME",
        "XDG_STATE_HOME",
        "XDG_RUNTIME_DIR",
    ):
        path = Path(os.environ[key])
        assert path.is_relative_to(tmp_path)
        assert stat.S_IMODE(path.stat().st_mode) == 0o700
    assert str(tmp_path) in os.environ["DBUS_SYSTEM_BUS_ADDRESS"]
    assert str(tmp_path) in os.environ["DBUS_SESSION_BUS_ADDRESS"]


def test_network_is_denied_by_default():
    with socket.socket() as sock, pytest.raises(AssertionError, match="networks"):
        sock.connect(("127.0.0.1", 12345))


def test_dns_and_connect_ex_are_denied():
    with pytest.raises(AssertionError, match="networks"):
        socket.getaddrinfo("example.com", 443)
    with socket.socket() as sock, pytest.raises(AssertionError, match="networks"):
        sock.connect_ex(("127.0.0.1", 12345))
    with socket.socket(type=socket.SOCK_DGRAM) as sock:
        with pytest.raises(AssertionError, match="networks"):
            sock.sendto(b"test", ("127.0.0.1", 12345))


@pytest.mark.local_network
def test_marked_local_fixtures_can_use_loopback_but_not_external_addresses():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        with socket.create_connection(listener.getsockname()):
            connection, _ = listener.accept()
            connection.close()
    with socket.socket() as sock, pytest.raises(AssertionError, match="networks"):
        sock.connect(("203.0.113.1", 443))


def test_fakes_do_not_launch_processes(fake_clock, fake_process):
    fake_clock.advance(0.5)
    assert fake_clock() == 0.5
    fake_process.send_signal(15)
    assert fake_process.signals == [15]
    assert fake_process.poll() is None
    fake_process.finish()
    assert fake_process.poll() == 0
