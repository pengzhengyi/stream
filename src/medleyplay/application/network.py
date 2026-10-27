"""The network the server is on, read from macOS's own commands.

The network is the first physical network service, in the service order, that
has a router; a VPN, a bridge, or a virtual interface never counts. It is known
by its subnet and its router's hardware address. Each reader is a pure function
of a command's output, so the tests read recorded output; `run_command` runs
them, each in the C locale with a short timeout.
"""

# cspell:ignore getinfo listnetworkserviceorder networksetup utun vmenet

import os
import re
import subprocess  # nosec B404 -- runs fixed system commands, never a shell
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from ipaddress import AddressValueError, IPv4Network, NetmaskValueError
from typing import Final

from medleyplay.domain.mode import UNREAD, Network, NetworkKind, Unread

COMMAND_TIMEOUT: Final = 3.0
"""Seconds a command may take before it counts as failed."""
VIRTUAL_DEVICES: Final = ("utun", "bridge", "vmenet", "docker", "lo")

Commands = Callable[[Sequence[str]], str | None]
"""Run a command and answer its output, or `None` when it failed or timed out."""

_SERVICE = re.compile(
    r"^\((?P<order>\d+|\*)\) (?P<name>.+)\n"
    r"\(Hardware Port: (?P<port>[^,]*), Device: (?P<device>[^)]*)\)",
    re.MULTILINE,
)
_FIELD = re.compile(r"^(?P<name>IP address|Subnet mask|Router): (?P<value>\S+)$", re.MULTILINE)
_ARP = re.compile(r"\) at (?P<address>[0-9A-Fa-f]{1,2}(?::[0-9A-Fa-f]{1,2}){5}) ")


@dataclass(frozen=True)
class NetworkService:
    """A network service, as the service order lists it; `device` is `None` for a VPN."""

    name: str
    port: str
    device: str | None
    enabled: bool

    @property
    def physical(self) -> bool:
        """Return whether the service is a real network interface, not a tunnel or a bridge."""
        return self.device is not None and not self.device.startswith(VIRTUAL_DEVICES)

    @property
    def kind(self) -> NetworkKind:
        """Return whether the service is Wi-Fi, a cable, or neither that the port says."""
        if self.port == "Wi-Fi":
            return NetworkKind.WIFI
        if "LAN" in self.port or "Ethernet" in self.port:
            return NetworkKind.WIRED
        return NetworkKind.UNKNOWN


@dataclass(frozen=True)
class ServiceInfo:
    """A service's subnet and its router's IP address."""

    subnet: IPv4Network
    router: str


def parse_service_order(output: str) -> list[NetworkService]:
    """Return each service `networksetup -listnetworkserviceorder` lists, in order."""
    return [
        NetworkService(
            name=match["name"],
            port=match["port"],
            device=match["device"] or None,
            enabled=match["order"] != "*",
        )
        for match in _SERVICE.finditer(output)
    ]


def parse_service_info(output: str) -> ServiceInfo | None:
    """Return the subnet and router `networksetup -getinfo` gives, if it gives a router."""
    fields = {match["name"]: match["value"] for match in _FIELD.finditer(output)}
    address, mask, router = (fields.get(name) for name in ("IP address", "Subnet mask", "Router"))
    if address is None or mask is None or router is None or router == "none":
        return None
    try:
        subnet = IPv4Network(f"{address}/{mask}", strict=False)
    except (AddressValueError, NetmaskValueError, ValueError):
        return None
    return ServiceInfo(subnet, router)


def parse_arp(output: str) -> str | None:
    """Return the hardware address `arp -n` gives, written in full in lower case, if it has one.

    macOS drops leading zeros, so `2:f:c4:d5:e6:7` is written `02:0f:c4:d5:e6:07`.
    """
    found = _ARP.search(output)
    if found is None:
        return None
    return ":".join(part.zfill(2) for part in found["address"].lower().split(":"))


def read_network(run: Commands) -> Network | Unread | None:
    """Return the network the server is on, `None` for none, or `UNREAD` if it can't be told.

    When the ARP cache doesn't hold the router, as after a wake or a join, the
    router is pinged once, since it is on the local network, and asked again.
    """
    order = run(["networksetup", "-listnetworkserviceorder"])
    if order is None:
        return UNREAD
    for service in parse_service_order(order):
        if not (service.enabled and service.physical):
            continue
        output = run(["networksetup", "-getinfo", service.name])
        if output is None:
            # A service before this one may be the network, so which one it is can't be told.
            return UNREAD
        info = parse_service_info(output)
        if info is None:
            continue
        router = _router_address(run, info.router)
        if router is None:
            run(["ping", "-c", "1", "-t", "1", info.router])
            router = _router_address(run, info.router)
        return Network(service.kind, info.subnet, router)
    return None


def _router_address(run: Commands, router: str) -> str | None:
    arp = run(["arp", "-n", router])
    return None if arp is None else parse_arp(arp)


def run_command(args: Sequence[str]) -> str | None:
    """Run a command in the C locale and answer its output, or `None` if it failed or timed out."""
    try:
        done = subprocess.run(  # noqa: S603  # nosec B603 -- fixed arguments, no shell
            list(args),
            capture_output=True,
            text=True,
            timeout=COMMAND_TIMEOUT,
            env={**os.environ, "LC_ALL": "C"},
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return done.stdout if done.returncode == 0 else None
