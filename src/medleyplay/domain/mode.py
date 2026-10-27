"""The Mode: whether medleyplay may contact music sites now.

`decide` is a pure function of the Mode before, the setting, what is known of the
network, the metered networks, and the time. Going Offline takes effect at once;
coming back Online waits until the facts have said Online for a while, longer
after each flap:

```text
12:00:00  facts Online    -> settling, Online at 12:00:30
12:00:10  no network      -> Offline, a flap: the next wait is 60 seconds
12:00:20  facts Online    -> settling, Online at 12:01:20
```
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum, StrEnum
from ipaddress import IPv4Network
from typing import Final

FIRST_WAIT: Final = timedelta(seconds=30)
"""How long the facts must say Online before the Mode is, after a calm time."""
LONGEST_WAIT: Final = timedelta(minutes=2)
CALM: Final = timedelta(minutes=5)
"""How long without a flap brings the wait back to the first."""
HOTSPOT_SUBNETS: Final = (IPv4Network("172.20.10.0/28"), IPv4Network("192.168.43.0/24"))
"""The subnets an iPhone's and an Android phone's hotspots usually use."""


class ModeSetting(StrEnum):
    """What the admin chose: decide from the network, or always Online or Offline."""

    AUTO = "auto"
    ONLINE = "online"
    OFFLINE = "offline"


class Reason(StrEnum):
    """Why the Mode is what it is."""

    SET_ONLINE = "set_online"
    SET_OFFLINE = "set_offline"
    ONLINE = "online"
    NO_NETWORK = "no_network"
    METERED = "metered"
    UNKNOWN_NETWORK = "unknown_network"
    UNREACHABLE = "unreachable"
    SETTLING = "settling"


class NetworkKind(StrEnum):
    """How the server is connected to the network."""

    WIFI = "wifi"
    WIRED = "wired"
    UNKNOWN = "unknown"


class Unread(Enum):
    """The network couldn't be read, as on a system other than macOS."""

    UNREAD = "unread"


UNREAD: Final = Unread.UNREAD


@dataclass(frozen=True)
class NetworkKey:
    """What a network is known by: its router's hardware address and its subnet."""

    router: str
    subnet: IPv4Network


@dataclass(frozen=True)
class Network:
    """The network the server is on; `router` is its router's hardware address, if read."""

    kind: NetworkKind
    subnet: IPv4Network
    router: str | None

    @property
    def key(self) -> NetworkKey | None:
        """Return what the network is known by, or `None` when its router's address is unknown."""
        return None if self.router is None else NetworkKey(self.router, self.subnet)

    @property
    def hotspot_like(self) -> bool:
        """Return whether the network is on a phone hotspot's usual subnet."""
        return any(self.subnet.subnet_of(hotspot) for hotspot in HOTSPOT_SUBNETS)


@dataclass(frozen=True)
class Facts:
    """What is known now: the network, `None` for none, and whether the internet was reached."""

    network: Network | Unread | None
    reachable: bool


@dataclass(frozen=True)
class Mode:
    """What the Mode is, why, and what deciding the next one needs to remember.

    `since` is when `online` last changed; `online_at`, while settling, is when it
    goes Online if nothing changes. `wait` is how long the next settling lasts,
    `flapped_at` when the facts last flapped, and `last_metered` whether the last
    network known was metered.
    """

    setting: ModeSetting
    online: bool
    reason: Reason
    since: datetime
    network: Network | None = None
    metered_as: str | None = None
    online_at: datetime | None = None
    wait: timedelta = FIRST_WAIT
    flapped_at: datetime | None = None
    last_metered: bool = False


def starting(setting: ModeSetting, now: datetime) -> Mode:
    """Return the Mode a server starts with: Offline, since nothing has been checked yet."""
    return Mode(setting=setting, online=False, reason=Reason.UNREACHABLE, since=now)


def decide(
    previous: Mode,
    setting: ModeSetting,
    facts: Facts,
    metered: Mapping[NetworkKey, str],
    now: datetime,
) -> Mode:
    """Return the Mode now, given the one before and what is known.

    `metered` names each network marked metered. Call it again at `online_at`
    to go Online once the wait is over.
    """
    network = facts.network if isinstance(facts.network, Network) else None
    key = None if network is None else network.key
    metered_as = None if key is None else metered.get(key)
    last_metered = previous.last_metered if key is None else metered_as is not None
    calm = previous.flapped_at is None or now - previous.flapped_at >= CALM
    wait = FIRST_WAIT if calm else previous.wait

    def become(
        *, online: bool, reason: Reason, online_at: datetime | None = None, flapped: bool = False
    ) -> Mode:
        return Mode(
            setting=setting,
            online=online,
            reason=reason,
            since=previous.since if previous.online is online else now,
            network=network,
            metered_as=metered_as,
            online_at=online_at,
            wait=min(2 * wait, LONGEST_WAIT) if flapped else wait,
            flapped_at=now if flapped else previous.flapped_at,
            last_metered=last_metered,
        )

    if setting is ModeSetting.ONLINE:
        return become(online=True, reason=Reason.SET_ONLINE)
    if setting is ModeSetting.OFFLINE:
        return become(online=False, reason=Reason.SET_OFFLINE)

    verdict = _verdict(facts, network, key, metered_as=metered_as, last_metered=last_metered)
    was_auto = previous.setting is ModeSetting.AUTO
    if verdict is not Reason.ONLINE:
        # A flap is the facts turning Offline while settling, or soon after going Online.
        flapped = was_auto and (
            previous.reason is Reason.SETTLING or (previous.online and now - previous.since < CALM)
        )
        return become(online=False, reason=verdict, flapped=flapped)

    # A change of the setting takes effect at once, as does staying Online.
    if previous.online or not was_auto:
        return become(online=True, reason=Reason.ONLINE)
    online_at = (
        previous.online_at
        if previous.reason is Reason.SETTLING and previous.online_at is not None
        else now + wait
    )
    if now >= online_at:
        return become(online=True, reason=Reason.ONLINE)
    return become(online=False, reason=Reason.SETTLING, online_at=online_at)


def _verdict(
    facts: Facts,
    network: Network | None,
    key: NetworkKey | None,
    *,
    metered_as: str | None,
    last_metered: bool,
) -> Reason:
    """Return what the facts alone say, `ONLINE` or why not."""
    if facts.network is None:
        return Reason.NO_NETWORK
    if key is None and last_metered:
        # Not knowing the network fails safe only after a metered one.
        return Reason.UNKNOWN_NETWORK
    if network is not None and metered_as is not None:
        return Reason.METERED
    return Reason.ONLINE if facts.reachable else Reason.UNREACHABLE
