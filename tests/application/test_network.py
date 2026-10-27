"""Reading the network the server is on from the output of macOS's own commands."""

# cspell:ignore getinfo ifscope listnetworkserviceorder macsys networksetup tailscale utun vmenet
# cspell:ignore wireguard

import sys
from collections.abc import Mapping, Sequence
from ipaddress import IPv4Network

import pytest

from medleyplay.application.network import (
    NetworkService,
    ServiceInfo,
    parse_arp,
    parse_service_info,
    parse_service_order,
    read_network,
    run_command,
)
from medleyplay.domain.mode import UNREAD, Network, NetworkKind


def service_order_behind_vpns() -> str:
    """`networksetup -listnetworkserviceorder` on a MacBook with cables, Wi-Fi, and three VPNs.

    The VPNs come first, as a VPN app puts itself; they have no device, so they never count.
    """
    return """\
An asterisk (*) denotes that a network service is disabled.
(1) Tailscale
(Hardware Port: io.tailscale.ipn.macsys, Device: )

(2) USB 10/100/1000 LAN
(Hardware Port: USB 10/100/1000 LAN, Device: en7)

(*) ThinkPad Lan
(Hardware Port: ThinkPad Lan, Device: en6)

(3) Wi-Fi
(Hardware Port: Wi-Fi, Device: en0)

(4) Thunderbolt Bridge
(Hardware Port: Thunderbolt Bridge, Device: bridge0)

(5) client
(Hardware Port: com.wireguard.macos, Device: )

"""


def wifi_at_home() -> str:
    """`networksetup -getinfo Wi-Fi` on the home Wi-Fi: `192.168.31.240/24`, router `.1`."""
    return """\
DHCP Configuration
IP address: 192.168.31.240
Subnet mask: 255.255.255.0
Router: 192.168.31.1
Client ID:
IPv6: Automatic
IPv6 IP address: none
IPv6 Router: none
Wi-Fi ID: 02:00:00:00:00:02
"""


def wifi_on_iphone_hotspot() -> str:
    """`networksetup -getinfo Wi-Fi` on an iPhone hotspot: `172.20.10.2/28`, router `.1`."""
    return """\
DHCP Configuration
IP address: 172.20.10.2
Subnet mask: 255.255.255.240
Router: 172.20.10.1
Client ID:
IPv6: Automatic
IPv6 IP address: none
IPv6 Router: none
Wi-Fi ID: 02:00:00:00:00:02
"""


def cable_unplugged() -> str:
    """`networksetup -getinfo` for a cable with nothing at the other end: no address, no router."""
    return """\
DHCP Configuration
Client ID:
IPv6: Automatic
IPv6 IP address: none
IPv6 Router: none
"""


def wifi_without_router() -> str:
    """`networksetup -getinfo Wi-Fi` joined to a network that hands out no router."""
    return """\
DHCP Configuration
IP address: 169.254.10.20
Subnet mask: 255.255.0.0
Router: none
Client ID:
"""


def home_router_arp() -> str:
    """`arp -n 192.168.31.1` once the router has answered a ping."""
    return "? (192.168.31.1) at a2:b3:c4:d5:e6:f7 on en0 ifscope [ethernet]\n"


class FakeCommands:
    """Answers each command from `answers`; one not listed fails, as a command that timed out."""

    def __init__(self, answers: Mapping[tuple[str, ...], str | None]) -> None:
        self.answers = answers
        self.ran: list[tuple[str, ...]] = []

    def __call__(self, args: Sequence[str]) -> str | None:
        self.ran.append(tuple(args))
        return self.answers.get(tuple(args))


ORDER = ("networksetup", "-listnetworkserviceorder")
CABLE = ("networksetup", "-getinfo", "USB 10/100/1000 LAN")
WIFI = ("networksetup", "-getinfo", "Wi-Fi")
PING_HOME = ("ping", "-c", "1", "-t", "1", "192.168.31.1")
ARP_HOME = ("arp", "-n", "192.168.31.1")


class TestParsing:
    def test_lists_each_service_in_order_with_its_port_and_device(self) -> None:
        services = parse_service_order(service_order_behind_vpns())

        assert services == [
            NetworkService("Tailscale", "io.tailscale.ipn.macsys", None, enabled=True),
            NetworkService("USB 10/100/1000 LAN", "USB 10/100/1000 LAN", "en7", enabled=True),
            NetworkService("ThinkPad Lan", "ThinkPad Lan", "en6", enabled=False),
            NetworkService("Wi-Fi", "Wi-Fi", "en0", enabled=True),
            NetworkService("Thunderbolt Bridge", "Thunderbolt Bridge", "bridge0", enabled=True),
            NetworkService("client", "com.wireguard.macos", None, enabled=True),
        ]

    @pytest.mark.parametrize(
        ("device", "physical"),
        [
            ("en0", True),
            ("en7", True),
            (None, False),
            ("utun4", False),
            ("bridge0", False),
            ("vmenet0", False),
            ("docker0", False),
            ("lo0", False),
        ],
    )
    def test_counts_only_a_physical_device(
        self,
        device: str | None,
        physical: bool,  # noqa: FBT001 -- a parameter of the test
    ) -> None:
        assert NetworkService("A", "A", device, enabled=True).physical is physical

    @pytest.mark.parametrize(
        ("port", "kind"),
        [
            ("Wi-Fi", NetworkKind.WIFI),
            ("USB 10/100/1000 LAN", NetworkKind.WIRED),
            ("Thunderbolt Ethernet Slot 1", NetworkKind.WIRED),
            ("iPhone USB", NetworkKind.UNKNOWN),
        ],
    )
    def test_tells_wifi_from_a_cable_by_the_hardware_port(
        self, port: str, kind: NetworkKind
    ) -> None:
        assert NetworkService(port, port, "en5", enabled=True).kind is kind

    def test_reads_a_services_subnet_and_router(self) -> None:
        info = parse_service_info(wifi_on_iphone_hotspot())

        assert info == ServiceInfo(IPv4Network("172.20.10.0/28"), "172.20.10.1")

    @pytest.mark.parametrize("output", [cable_unplugged(), wifi_without_router(), ""])
    def test_reads_no_router_for_a_service_without_one(self, output: str) -> None:
        assert parse_service_info(output) is None

    @pytest.mark.parametrize(
        ("output", "address"),
        [
            (home_router_arp(), "a2:b3:c4:d5:e6:f7"),
            ("? (172.20.10.1) at 2:f:c4:d5:E6:7 on en0 ifscope [ethernet]\n", "02:0f:c4:d5:e6:07"),
            ("? (192.168.31.1) at (incomplete) on en0 ifscope [ethernet]\n", None),
            ("192.168.31.1 (192.168.31.1) -- no entry\n", None),
        ],
    )
    def test_reads_the_routers_hardware_address_written_in_full(
        self, output: str, address: str | None
    ) -> None:
        assert parse_arp(output) == address


class TestReadingTheNetwork:
    def test_is_the_first_physical_service_with_a_router_past_the_vpns(self) -> None:
        run = FakeCommands(
            {
                ORDER: service_order_behind_vpns(),
                CABLE: cable_unplugged(),
                WIFI: wifi_at_home(),
                PING_HOME: "",
                ARP_HOME: home_router_arp(),
            }
        )

        network = read_network(run)

        assert network == Network(
            NetworkKind.WIFI, IPv4Network("192.168.31.0/24"), "a2:b3:c4:d5:e6:f7"
        )

    def test_reads_the_routers_address_without_a_ping_when_arp_has_it(self) -> None:
        run = FakeCommands(
            {
                ORDER: service_order_behind_vpns(),
                CABLE: "",
                WIFI: wifi_at_home(),
                ARP_HOME: home_router_arp(),
            }
        )

        read_network(run)

        assert PING_HOME not in run.ran

    def test_pings_the_router_and_asks_again_when_arp_doesnt_have_it(self) -> None:
        run = FakeCommands({ORDER: service_order_behind_vpns(), WIFI: wifi_at_home(), CABLE: ""})

        read_network(run)

        assert run.ran[-3:] == [ARP_HOME, PING_HOME, ARP_HOME]

    def test_keeps_the_network_without_its_routers_address_when_arp_has_none(self) -> None:
        run = FakeCommands({ORDER: service_order_behind_vpns(), CABLE: "", WIFI: wifi_at_home()})

        network = read_network(run)

        assert network == Network(NetworkKind.WIFI, IPv4Network("192.168.31.0/24"), None)

    def test_is_none_when_no_physical_service_has_a_router(self) -> None:
        run = FakeCommands(
            {ORDER: service_order_behind_vpns(), CABLE: cable_unplugged(), WIFI: cable_unplugged()}
        )

        assert read_network(run) is None

    def test_is_unread_when_the_service_order_cant_be_read(self) -> None:
        assert read_network(FakeCommands({})) is UNREAD

    def test_is_unread_when_a_service_before_the_network_cant_be_read(self) -> None:
        run = FakeCommands({ORDER: service_order_behind_vpns(), WIFI: wifi_at_home()})

        assert read_network(run) is UNREAD


class TestRunningACommand:
    def test_answers_its_output(self) -> None:
        assert run_command([sys.executable, "-c", "print('ok')"]) == "ok\n"

    def test_answers_none_when_it_fails(self) -> None:
        assert run_command([sys.executable, "-c", "raise SystemExit(1)"]) is None

    def test_answers_none_when_it_cant_start(self) -> None:
        assert run_command(["medleyplay-no-such-command"]) is None

    def test_runs_in_the_c_locale(self) -> None:
        output = run_command([sys.executable, "-c", "import os; print(os.environ['LC_ALL'])"])

        assert output == "C\n"


@pytest.mark.skipif(sys.platform != "darwin", reason="reads this Mac's own network")
def test_reads_this_macs_network() -> None:
    network = read_network(run_command)

    assert network is None or isinstance(network, Network)
