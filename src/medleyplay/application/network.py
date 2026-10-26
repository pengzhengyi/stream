"""The network the server is on, read from macOS's own commands.

Each reader is a pure function of a command's output, so the tests read recorded
output; the probe runs the commands, each with a short timeout.
"""

import re
from dataclasses import dataclass

_FIELD = re.compile(r"^\s*(?P<name>[a-z ]+):\s*(?P<value>\S+)", re.MULTILINE)
_PORT = re.compile(r"^Hardware Port: (?P<port>.+)\nDevice: (?P<device>\S+)", re.MULTILINE)
_ARP = re.compile(r"\) at (?P<address>[0-9A-Fa-f]{1,2}(?::[0-9A-Fa-f]{1,2}){5}) ")


@dataclass(frozen=True)
class DefaultRoute:
    """Where the default route goes: the gateway's IP address and the interface to it."""

    gateway: str
    interface: str


def parse_default_route(output: str) -> DefaultRoute | None:
    """Return the gateway and interface `route -n get default` names, if it names both."""
    fields = {match["name"]: match["value"] for match in _FIELD.finditer(output)}
    gateway = fields.get("gateway")
    interface = fields.get("interface")
    return None if gateway is None or interface is None else DefaultRoute(gateway, interface)


def parse_hardware_ports(output: str) -> dict[str, str]:
    """Return each device's hardware port, as `networksetup -listallhardwareports` lists them."""
    return {match["device"]: match["port"] for match in _PORT.finditer(output)}


def parse_arp(output: str) -> str | None:
    """Return the hardware address `arp -n` gives, written in full in lower case, if it has one.

    macOS drops leading zeros, so `2:f:c4:d5:e6:7` is written `02:0f:c4:d5:e6:07`.
    """
    found = _ARP.search(output)
    if found is None:
        return None
    return ":".join(part.zfill(2) for part in found["address"].lower().split(":"))
