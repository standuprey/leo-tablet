"""Tests default to private storage, no host D-Bus and no internet connections."""

import ipaddress
import socket
from dataclasses import dataclass, field
from pathlib import Path

import pytest


def pytest_addoption(parser):
    for kind in ("display", "wayland", "hardware"):
        parser.addoption(f"--run-{kind}", action="store_true", default=False)


def pytest_collection_modifyitems(config, items):
    for item in items:
        for kind in ("display", "wayland", "hardware"):
            if item.get_closest_marker(kind) and not config.getoption(f"--run-{kind}"):
                item.add_marker(pytest.mark.skip(reason=f"requires --run-{kind}"))


@pytest.fixture(autouse=True)
def isolated_environment(tmp_path, monkeypatch):
    for variable in (
        "HOME",
        "XDG_DATA_HOME",
        "XDG_CONFIG_HOME",
        "XDG_CACHE_HOME",
        "XDG_STATE_HOME",
        "XDG_RUNTIME_DIR",
    ):
        directory = tmp_path / variable.lower()
        directory.mkdir(mode=0o700)
        monkeypatch.setenv(variable, str(directory))
    address = f"unix:path={tmp_path}/no-host-bus"
    monkeypatch.setenv("DBUS_SYSTEM_BUS_ADDRESS", address)
    monkeypatch.setenv("DBUS_SESSION_BUS_ADDRESS", address)
    monkeypatch.delenv("DBUS_STARTER_ADDRESS", raising=False)


@pytest.fixture(autouse=True)
def no_external_network(request, monkeypatch):
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex
    original_sendto = socket.socket.sendto
    original_resolve = socket.getaddrinfo
    local_only = request.node.get_closest_marker("local_network") is not None

    def check_host(host):
        try:
            loopback = ipaddress.ip_address(host).is_loopback
        except ValueError:
            loopback = host == "localhost"
        if not (local_only and loopback):
            raise AssertionError("Tests cannot connect to external/host networks")

    def check_address(sock, address):
        if sock.family in (socket.AF_INET, socket.AF_INET6):
            check_host(address[0])
        elif address in ("/run/dbus/system_bus_socket", "/var/run/dbus/system_bus_socket"):
            raise AssertionError("Tests cannot connect to the host system bus")

    def connect(sock, address):
        check_address(sock, address)
        return original_connect(sock, address)

    def connect_ex(sock, address):
        check_address(sock, address)
        return original_connect_ex(sock, address)

    def sendto(sock, data, *args):
        check_address(sock, args[-1])
        return original_sendto(sock, data, *args)

    def resolve(host, *args, **kwargs):
        check_host(host)
        return original_resolve(host, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket.socket, "connect_ex", connect_ex)
    monkeypatch.setattr(socket.socket, "sendto", sendto)
    monkeypatch.setattr(socket, "getaddrinfo", resolve)


@dataclass
class FakeClock:
    value: float = 0.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


@dataclass
class FakeProcess:
    pid: int = 70001
    returncode: int | None = None
    signals: list[int] = field(default_factory=list)

    def poll(self) -> int | None:
        return self.returncode

    def send_signal(self, signal: int) -> None:
        self.signals.append(signal)

    def finish(self, returncode: int = 0) -> None:
        self.returncode = returncode


@pytest.fixture
def fake_clock():
    return FakeClock()


@pytest.fixture
def fake_process():
    return FakeProcess()


@pytest.fixture
def private_data_dir() -> Path:
    import os

    return Path(os.environ["XDG_DATA_HOME"])
