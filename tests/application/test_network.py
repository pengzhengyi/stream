"""Reading the network the server is on from the output of macOS's own commands."""

import pytest

from medleyplay.application.network import (
    DefaultRoute,
    parse_arp,
    parse_default_route,
    parse_hardware_ports,
)


def on_wifi_route() -> str:
    """`route -n get default` on a Mac whose default route is Wi-Fi to a home router.

    ```text
       route to: default
    destination: default
           mask: default
        gateway: 192.168.31.1
      interface: en0
          flags: <UP,GATEWAY,DONE,STATIC,PRCLONING,IFSCOPE,GLOBAL>
    ```
    """
    return """\
   route to: default
destination: default
       mask: default
    gateway: 192.168.31.1
  interface: en0
      flags: <UP,GATEWAY,DONE,STATIC,PRCLONING,IFSCOPE,GLOBAL>
 recvpipe  sendpipe  ssthresh  rtt,msec    rttvar  hopcount      mtu     expire
       0         0         0         0         0         0      1500         0
"""


def hardware_ports() -> str:
    """`networksetup -listallhardwareports` on a MacBook with Wi-Fi and Thunderbolt ports."""
    return """
Hardware Port: Thunderbolt Bridge
Device: bridge0
Ethernet Address: 02:00:00:00:00:01

Hardware Port: Wi-Fi
Device: en0
Ethernet Address: 02:00:00:00:00:02

Hardware Port: USB 10/100/1000 LAN
Device: en7
Ethernet Address: 02:00:00:00:00:03

VLAN Configurations
===================
"""


def test_reads_the_default_routes_gateway_and_interface() -> None:
    assert parse_default_route(on_wifi_route()) == DefaultRoute("192.168.31.1", "en0")


@pytest.mark.parametrize(
    "output",
    [
        "route: writing to routing socket: not in table\n",
        "",
        "   route to: default\n  interface: utun4\n",
    ],
)
def test_finds_no_gateway_without_a_default_route_through_one(output: str) -> None:
    assert parse_default_route(output) is None


def test_reads_each_devices_hardware_port() -> None:
    ports = parse_hardware_ports(hardware_ports())

    assert ports == {"bridge0": "Thunderbolt Bridge", "en0": "Wi-Fi", "en7": "USB 10/100/1000 LAN"}


@pytest.mark.parametrize(
    ("output", "address"),
    [
        ("? (192.168.31.1) at a2:b3:c4:d5:e6:f7 on en0 ifscope [ethernet]\n", "a2:b3:c4:d5:e6:f7"),
        ("? (172.20.10.1) at 2:f:c4:d5:E6:7 on en0 ifscope [ethernet]\n", "02:0f:c4:d5:e6:07"),
        ("? (192.168.31.1) at (incomplete) on en0 ifscope [ethernet]\n", None),
        ("192.168.31.1 (192.168.31.1) -- no entry\n", None),
    ],
)
def test_reads_the_gateways_hardware_address_written_in_full(
    output: str, address: str | None
) -> None:
    assert parse_arp(output) == address
