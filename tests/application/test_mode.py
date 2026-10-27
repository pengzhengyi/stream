"""The Mode service: reading the network and the internet, deciding, and the Mode's settings."""

import threading
from datetime import timedelta

import pytest
from sqlalchemy.orm import Session, sessionmaker

from medleyplay.application.accounts import AccountService
from medleyplay.application.mode import (
    CHECK_AFTER_FAILURE,
    CHECK_WHILE_ONLINE,
    NETWORK_POLL,
    ModeService,
)
from medleyplay.domain.accounts import Account
from medleyplay.domain.errors import ConflictError, ForbiddenError, InvalidInputError
from medleyplay.domain.mode import (
    FIRST_WAIT,
    UNREAD,
    ModeSetting,
    ModeSettings,
    Reason,
)
from tests.support.factories import NetworkFactory, NewAccountFactory
from tests.support.fakes import FakeClock, FakeInternet, FakeNetwork


def _alice_and_bob(accounts: AccountService) -> tuple[Account, Account]:
    """Return Alice, the admin, and Bob, a member."""
    alice = accounts.create_first_admin(NewAccountFactory.admin()).account
    return alice, accounts.create_account(alice, NewAccountFactory.member())


def _settled(mode: ModeService, clock: FakeClock) -> None:
    """Tick, and tick again once the first wait is over, as the service's thread does."""
    mode.tick()
    clock.advance(FIRST_WAIT)
    mode.tick()


class TestDeciding:
    def test_starts_offline_and_settles_before_going_online(
        self, mode: ModeService, clock: FakeClock
    ) -> None:
        mode.tick()
        settling = mode.now().mode
        clock.advance(FIRST_WAIT)
        mode.tick()

        assert (settling.online, settling.reason) == (False, Reason.SETTLING)
        assert (mode.now().mode.online, mode.now().mode.since) == (True, clock())

    def test_wakes_when_settling_ends_before_the_next_read(
        self, mode: ModeService, clock: FakeClock
    ) -> None:
        online_at = clock() + FIRST_WAIT
        mode.tick()
        clock.advance(FIRST_WAIT - timedelta(seconds=2))

        wake = mode.tick()

        assert wake == online_at

    def test_wakes_to_read_the_network_again_while_online(
        self, mode: ModeService, clock: FakeClock
    ) -> None:
        _settled(mode, clock)

        assert mode.tick() == clock() + NETWORK_POLL

    def test_goes_offline_at_the_tick_that_reads_no_network(
        self, mode: ModeService, clock: FakeClock, network: FakeNetwork
    ) -> None:
        _settled(mode, clock)
        network.network = None

        mode.tick()

        assert (mode.now().mode.online, mode.now().mode.reason) == (False, Reason.NO_NETWORK)

    def test_tells_of_a_change_of_mode_and_not_of_a_tick_that_changes_nothing(
        self, mode: ModeService, clock: FakeClock, told: list[str]
    ) -> None:
        _settled(mode, clock)
        mode.tick()

        assert told == ["mode", "mode"]


class TestCheckingTheInternet:
    def test_checks_at_the_first_tick(self, mode: ModeService, internet: FakeInternet) -> None:
        mode.tick()

        assert internet.checks == 1

    def test_checks_again_only_once_online_and_quiet_for_the_interval(
        self, mode: ModeService, clock: FakeClock, internet: FakeInternet
    ) -> None:
        mode.tick()
        clock.advance(CHECK_WHILE_ONLINE - timedelta(seconds=1))
        mode.tick()
        checks_before = internet.checks
        clock.advance(timedelta(seconds=1))

        mode.tick()

        assert (checks_before, internet.checks) == (1, 2)

    def test_checks_again_soon_after_a_failed_check(
        self, mode: ModeService, clock: FakeClock, internet: FakeInternet
    ) -> None:
        internet.reachable = False
        mode.tick()
        clock.advance(CHECK_AFTER_FAILURE)

        mode.tick()

        assert internet.checks == 2
        assert mode.now().checked_at == clock()

    def test_checks_at_once_on_another_network(
        self, mode: ModeService, internet: FakeInternet, network: FakeNetwork
    ) -> None:
        mode.tick()
        network.network = NetworkFactory.iphone_hotspot()

        mode.tick()

        assert internet.checks == 2

    def test_checks_at_once_when_asked(self, mode: ModeService, internet: FakeInternet) -> None:
        mode.tick()
        mode.check_soon()

        mode.tick()

        assert internet.checks == 2

    def test_checks_nothing_while_the_setting_is_offline(
        self, mode: ModeService, accounts: AccountService, internet: FakeInternet
    ) -> None:
        alice, _ = _alice_and_bob(accounts)

        mode.put_setting(alice, ModeSetting.OFFLINE, revision=0)
        mode.tick()

        assert internet.checks == 0

    def test_checks_at_once_on_leaving_the_setting_offline(
        self, mode: ModeService, accounts: AccountService, internet: FakeInternet
    ) -> None:
        alice, _ = _alice_and_bob(accounts)
        mode.put_setting(alice, ModeSetting.OFFLINE, revision=0)

        mode.put_setting(alice, ModeSetting.AUTO, revision=1)

        assert internet.checks == 1
        assert mode.now().mode.online


class TestTheSetting:
    def test_is_auto_with_nothing_marked_until_saved(self, mode: ModeService) -> None:
        assert mode.settings() == ModeSettings(ModeSetting.AUTO, (), revision=0)

    def test_an_admin_sets_it_and_it_takes_effect_at_once(
        self, mode: ModeService, accounts: AccountService
    ) -> None:
        alice, _ = _alice_and_bob(accounts)

        saved = mode.put_setting(alice, ModeSetting.OFFLINE, revision=0)

        assert (saved.setting, saved.revision) == (ModeSetting.OFFLINE, 1)
        assert mode.now().mode.reason is Reason.SET_OFFLINE

    def test_a_stale_revision_is_refused(self, mode: ModeService, accounts: AccountService) -> None:
        alice, _ = _alice_and_bob(accounts)
        mode.put_setting(alice, ModeSetting.OFFLINE, revision=0)

        with pytest.raises(ConflictError, match="saved since revision 0"):
            mode.put_setting(alice, ModeSetting.ONLINE, revision=0)

    def test_a_member_cant_change_it(self, mode: ModeService, accounts: AccountService) -> None:
        _, bob = _alice_and_bob(accounts)

        with pytest.raises(ForbiddenError):
            mode.put_setting(bob, ModeSetting.OFFLINE, revision=0)


class TestMeteredNetworks:
    def test_an_admin_marks_the_network_the_server_is_on_and_auto_goes_offline(
        self, mode: ModeService, clock: FakeClock, accounts: AccountService, network: FakeNetwork
    ) -> None:
        alice, _ = _alice_and_bob(accounts)
        network.network = NetworkFactory.iphone_hotspot()
        _settled(mode, clock)

        marked = mode.mark_metered(alice, "  iPhone hotspot ")

        assert (marked.name, marked.key, marked.hotspot_like) == (
            "iPhone hotspot",
            NetworkFactory.iphone_hotspot().key,
            True,
        )
        assert mode.settings().metered == (marked,)
        assert (mode.now().mode.reason, mode.now().mode.metered_as) == (
            Reason.METERED,
            "iPhone hotspot",
        )

    def test_marking_a_marked_network_again_renames_it(
        self, mode: ModeService, accounts: AccountService
    ) -> None:
        alice, _ = _alice_and_bob(accounts)
        first = mode.mark_metered(alice, "Hotspot")

        again = mode.mark_metered(alice, "Phone")

        assert (again.id, again.name) == (first.id, "Phone")
        assert mode.settings().metered == (again,)

    def test_removing_a_mark_brings_auto_back_online_after_settling(
        self, mode: ModeService, clock: FakeClock, accounts: AccountService
    ) -> None:
        alice, _ = _alice_and_bob(accounts)
        marked = mode.mark_metered(alice, "Hotspot")

        mode.unmark(alice, marked.id)
        clock.advance(FIRST_WAIT)
        mode.tick()

        assert mode.settings().metered == ()
        assert mode.now().mode.online

    def test_removing_a_mark_already_gone_changes_nothing(
        self, mode: ModeService, accounts: AccountService
    ) -> None:
        alice, _ = _alice_and_bob(accounts)

        mode.unmark(alice, 7)

        assert mode.settings().revision == 0

    @pytest.mark.parametrize("name", ["", "   ", "x" * 65])
    def test_a_mark_needs_a_name_of_a_few_words(
        self, mode: ModeService, accounts: AccountService, name: str
    ) -> None:
        alice, _ = _alice_and_bob(accounts)

        with pytest.raises(InvalidInputError):
            mode.mark_metered(alice, name)

    @pytest.mark.parametrize(
        "reading", [UNREAD, None, NetworkFactory.home_wifi(router=None)], ids=str
    )
    def test_a_network_that_cant_be_told_apart_cant_be_marked(
        self,
        mode: ModeService,
        accounts: AccountService,
        network: FakeNetwork,
        reading: object,
    ) -> None:
        alice, _ = _alice_and_bob(accounts)
        network.network = reading  # type: ignore[assignment]

        with pytest.raises(ConflictError, match="can't tell"):
            mode.mark_metered(alice, "Hotspot")

    def test_a_member_cant_mark_one(self, mode: ModeService, accounts: AccountService) -> None:
        _, bob = _alice_and_bob(accounts)

        with pytest.raises(ForbiddenError):
            mode.mark_metered(bob, "Hotspot")


def test_its_thread_ticks_until_stopped(
    units: sessionmaker[Session], clock: FakeClock, network: FakeNetwork, internet: FakeInternet
) -> None:
    ticked = threading.Event()
    mode = ModeService(units, clock, probe=network, check=internet, on_change=ticked.set)

    mode.start()
    try:
        assert ticked.wait(5)
    finally:
        mode.stop()
