"""The Mode: what the setting and the network come to, and how it waits before going Online."""

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from ipaddress import IPv4Network

import pytest
from hypothesis import given
from hypothesis import strategies as st

from medleyplay.domain.mode import (
    CALM,
    FIRST_WAIT,
    LONGEST_WAIT,
    UNREAD,
    Facts,
    Mode,
    ModeSetting,
    Network,
    NetworkKey,
    NetworkKind,
    Reason,
    Unread,
    decide,
    starting,
)

NOW = datetime(2026, 10, 26, 12, tzinfo=UTC)
AUTO = ModeSetting.AUTO


def home_wifi() -> Network:
    """The household's Wi-Fi: router `192.168.31.1`, at `a2:b3:c4:d5:e6:f7`, on a /24."""
    return Network(NetworkKind.WIFI, IPv4Network("192.168.31.0/24"), "a2:b3:c4:d5:e6:f7")


def iphone_hotspot() -> Network:
    """An iPhone's Personal Hotspot: router `172.20.10.1`, on the iPhone's usual /28."""
    return Network(NetworkKind.WIFI, IPv4Network("172.20.10.0/28"), "02:0f:c4:d5:e6:07")


def hotspot_marked() -> Mapping[NetworkKey, str]:
    """The admin has marked the iPhone hotspot metered, as *iPhone hotspot*."""
    key = iphone_hotspot().key
    assert key is not None
    return {key: "iPhone hotspot"}


def on(network: Network | Unread | None, *, reachable: bool = True) -> Facts:
    return Facts(network=network, reachable=reachable)


def online_at_home() -> Mode:
    """Auto, Online on the home Wi-Fi since `NOW`, after a calm start."""
    settling = decide(starting(AUTO, NOW - FIRST_WAIT), AUTO, on(home_wifi()), {}, NOW - FIRST_WAIT)
    return decide(settling, AUTO, on(home_wifi()), {}, NOW)


def offline_on_hotspot() -> Mode:
    """Auto, Offline on the marked iPhone hotspot since `NOW`, after a long calm time at home."""
    calm = decide(online_at_home(), AUTO, on(home_wifi()), {}, NOW + CALM)
    return decide(calm, AUTO, on(iphone_hotspot()), hotspot_marked(), NOW + CALM)


class TestTheSetting:
    def test_online_is_online_at_once_even_on_a_metered_network(self) -> None:
        mode = decide(
            starting(ModeSetting.ONLINE, NOW),
            ModeSetting.ONLINE,
            on(iphone_hotspot()),
            hotspot_marked(),
            NOW,
        )

        assert (mode.online, mode.reason) == (True, Reason.SET_ONLINE)

    def test_offline_is_offline_at_once_on_any_network(self) -> None:
        mode = decide(online_at_home(), ModeSetting.OFFLINE, on(home_wifi()), {}, NOW)

        assert (mode.online, mode.reason, mode.since) == (False, Reason.SET_OFFLINE, NOW)

    def test_changing_to_auto_takes_effect_at_once_without_settling(self) -> None:
        set_offline = decide(online_at_home(), ModeSetting.OFFLINE, on(home_wifi()), {}, NOW)

        mode = decide(set_offline, AUTO, on(home_wifi()), {}, NOW + timedelta(seconds=1))

        assert (mode.online, mode.reason) == (True, Reason.ONLINE)


class TestAuto:
    def test_is_offline_without_a_network(self) -> None:
        mode = decide(online_at_home(), AUTO, on(None), {}, NOW)

        assert (mode.online, mode.reason) == (False, Reason.NO_NETWORK)

    def test_is_offline_on_a_network_marked_metered_and_says_its_mark(self) -> None:
        mode = decide(online_at_home(), AUTO, on(iphone_hotspot()), hotspot_marked(), NOW)

        assert (mode.online, mode.reason, mode.metered_as) == (
            False,
            Reason.METERED,
            "iPhone hotspot",
        )

    def test_is_offline_when_the_internet_is_unreachable(self) -> None:
        mode = decide(online_at_home(), AUTO, on(home_wifi(), reachable=False), {}, NOW)

        assert (mode.online, mode.reason) == (False, Reason.UNREACHABLE)

    def test_stays_offline_when_the_network_cant_be_read_after_a_metered_one(self) -> None:
        later = NOW + CALM + timedelta(minutes=10)

        mode = decide(offline_on_hotspot(), AUTO, on(UNREAD), hotspot_marked(), later)

        assert (mode.online, mode.reason) == (False, Reason.UNKNOWN_NETWORK)

    def test_stays_offline_when_the_router_cant_be_read_after_a_metered_network(self) -> None:
        unknown_router = Network(NetworkKind.WIFI, IPv4Network("192.168.31.0/24"), router=None)
        later = NOW + CALM + timedelta(minutes=10)

        mode = decide(offline_on_hotspot(), AUTO, on(unknown_router), hotspot_marked(), later)

        assert (mode.online, mode.reason) == (False, Reason.UNKNOWN_NETWORK)

    def test_goes_by_the_check_alone_when_the_network_is_never_known(self) -> None:
        settling = decide(starting(AUTO, NOW), AUTO, on(UNREAD), {}, NOW)

        mode = decide(settling, AUTO, on(UNREAD), {}, NOW + FIRST_WAIT)

        assert (mode.online, mode.reason) == (True, Reason.ONLINE)

    def test_comes_back_online_on_an_unmarked_network_after_a_metered_one(self) -> None:
        later = NOW + CALM + timedelta(minutes=10)
        settling = decide(offline_on_hotspot(), AUTO, on(home_wifi()), hotspot_marked(), later)

        mode = decide(settling, AUTO, on(home_wifi()), hotspot_marked(), later + FIRST_WAIT)

        assert (mode.online, mode.network) == (True, home_wifi())


class TestComingBackOnline:
    def test_the_server_starts_offline_and_waits_before_going_online(self) -> None:
        mode = decide(starting(AUTO, NOW), AUTO, on(home_wifi()), {}, NOW)

        assert (mode.online, mode.reason, mode.online_at) == (
            False,
            Reason.SETTLING,
            NOW + FIRST_WAIT,
        )

    @pytest.mark.parametrize(("seconds", "online"), [(29, False), (31, True)])
    def test_goes_online_once_the_facts_said_online_for_the_wait(
        self,
        seconds: int,
        online: bool,  # noqa: FBT001 -- a parameter of the test
    ) -> None:
        settling = decide(starting(AUTO, NOW), AUTO, on(home_wifi()), {}, NOW)

        mode = decide(settling, AUTO, on(home_wifi()), {}, NOW + timedelta(seconds=seconds))

        assert mode.online is online

    def test_going_online_is_when_the_mode_changed(self) -> None:
        assert (online_at_home().since, online_at_home().online_at) == (NOW, None)

    def test_goes_offline_at_once(self) -> None:
        mode = decide(online_at_home(), AUTO, on(None), {}, NOW + timedelta(seconds=1))

        assert (mode.online, mode.since) == (False, NOW + timedelta(seconds=1))

    def test_a_flap_while_settling_doubles_the_next_wait(self) -> None:
        settling = decide(starting(AUTO, NOW), AUTO, on(home_wifi()), {}, NOW)
        flapped = decide(settling, AUTO, on(None), {}, NOW + timedelta(seconds=10))

        mode = decide(flapped, AUTO, on(home_wifi()), {}, NOW + timedelta(seconds=20))

        assert mode.online_at == NOW + timedelta(seconds=20) + 2 * FIRST_WAIT

    def test_going_offline_soon_after_going_online_is_a_flap(self) -> None:
        mode = decide(online_at_home(), AUTO, on(None), {}, NOW + CALM - timedelta(seconds=1))

        assert mode.wait == 2 * FIRST_WAIT

    def test_going_offline_after_a_calm_time_online_is_no_flap(self) -> None:
        mode = decide(online_at_home(), AUTO, on(None), {}, NOW + CALM)

        assert mode.wait == FIRST_WAIT

    def test_the_wait_doubles_no_further_than_the_longest(self) -> None:
        mode = decide(starting(AUTO, NOW), AUTO, on(home_wifi()), {}, NOW)
        for second in range(1, 20, 2):
            mode = decide(mode, AUTO, on(None), {}, NOW + timedelta(seconds=second))
            mode = decide(mode, AUTO, on(home_wifi()), {}, NOW + timedelta(seconds=second + 1))

        assert mode.wait == LONGEST_WAIT

    def test_five_calm_minutes_bring_the_wait_back_to_the_first(self) -> None:
        settling = decide(starting(AUTO, NOW), AUTO, on(home_wifi()), {}, NOW)
        flapped = decide(settling, AUTO, on(None), {}, NOW + timedelta(seconds=10))
        calm = NOW + timedelta(seconds=10) + CALM

        mode = decide(flapped, AUTO, on(home_wifi()), {}, calm)

        assert mode.online_at == calm + FIRST_WAIT


class TestTheNetwork:
    @pytest.mark.parametrize(
        ("subnet", "hotspot_like"),
        [
            ("172.20.10.0/28", True),
            ("192.168.43.0/24", True),
            ("192.168.31.0/24", False),
            ("172.20.0.0/16", False),
        ],
    )
    def test_is_hotspot_like_on_a_phone_hotspots_usual_subnet(
        self,
        subnet: str,
        hotspot_like: bool,  # noqa: FBT001 -- a parameter of the test
    ) -> None:
        network = Network(NetworkKind.WIFI, IPv4Network(subnet), "a2:b3:c4:d5:e6:f7")

        assert network.hotspot_like is hotspot_like

    def test_is_known_by_its_routers_hardware_address_and_subnet(self) -> None:
        assert home_wifi().key == NetworkKey("a2:b3:c4:d5:e6:f7", IPv4Network("192.168.31.0/24"))

    def test_is_unknown_without_its_routers_hardware_address(self) -> None:
        assert Network(NetworkKind.WIRED, IPv4Network("10.0.0.0/8"), router=None).key is None


_READINGS: list[Network | Unread | None] = [
    home_wifi(),
    iphone_hotspot(),
    Network(NetworkKind.WIFI, IPv4Network("192.168.31.0/24"), router=None),
    None,
    UNREAD,
]


@given(
    st.lists(
        st.tuples(
            st.sampled_from(_READINGS), st.booleans(), st.integers(min_value=0, max_value=400)
        ),
        max_size=40,
    )
)
def test_auto_is_never_online_where_it_must_not_be(steps: list[tuple[object, bool, int]]) -> None:
    metered = hotspot_marked()
    mode, now = starting(AUTO, NOW), NOW
    last_known_metered, facts_online_since = False, None
    for reading, reachable, seconds in steps:
        assert isinstance(reading, Network | Unread) or reading is None
        now += timedelta(seconds=seconds)
        key = reading.key if isinstance(reading, Network) else None
        unknown = reading is UNREAD or (isinstance(reading, Network) and key is None)
        if key is not None:
            last_known_metered = key in metered

        mode = decide(mode, AUTO, on(reading, reachable=reachable), metered, now)

        must_be_offline = (
            reading is None
            or (key is not None and key in metered)
            or (unknown and last_known_metered)
        )
        facts_online = not must_be_offline and reachable
        facts_online_since = (facts_online_since or now) if facts_online else None
        assert not (mode.online and must_be_offline)
        assert not mode.online or (
            facts_online_since is not None and now - facts_online_since >= FIRST_WAIT
        )
