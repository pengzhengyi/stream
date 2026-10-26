"""An Account's preferences: its own document, saved at the revision it was read."""

import pytest

from medleyplay.application.accounts import AccountService
from medleyplay.application.preferences import PreferencesService
from medleyplay.domain.accounts import Account
from medleyplay.domain.errors import ConflictError, InvalidInputError
from medleyplay.domain.preferences import Preferences
from tests.support.factories import NewAccountFactory

PLAY_ON_K = {"toggle": ("space", "k"), "mute": ("m",)}


def _alice_and_bob(accounts: AccountService) -> tuple[Account, Account]:
    """Return Alice, the admin, and Bob, a member."""
    alice = accounts.create_first_admin(NewAccountFactory.admin()).account
    return alice, accounts.create_account(alice, NewAccountFactory.member())


def test_preferences_never_saved_have_no_shortcuts_at_revision_zero(
    preferences: PreferencesService, accounts: AccountService
) -> None:
    alice, _ = _alice_and_bob(accounts)

    assert preferences.get(alice.id) == Preferences(shortcuts=None, revision=0)


def test_an_account_saves_its_shortcuts_at_the_revision_read_and_gets_the_next_one(
    preferences: PreferencesService, accounts: AccountService
) -> None:
    alice, _ = _alice_and_bob(accounts)

    saved = preferences.put(alice.id, Preferences(shortcuts=PLAY_ON_K, revision=0))

    assert saved == Preferences(shortcuts=PLAY_ON_K, revision=1)
    assert preferences.get(alice.id) == saved


def test_each_account_keeps_its_own_preferences(
    preferences: PreferencesService, accounts: AccountService
) -> None:
    alice, bob = _alice_and_bob(accounts)

    preferences.put(alice.id, Preferences(shortcuts=PLAY_ON_K, revision=0))

    assert preferences.get(bob.id) == Preferences(shortcuts=None, revision=0)


def test_saving_at_a_stale_revision_is_refused(
    preferences: PreferencesService, accounts: AccountService
) -> None:
    alice, _ = _alice_and_bob(accounts)
    preferences.put(alice.id, Preferences(shortcuts=PLAY_ON_K, revision=0))

    with pytest.raises(ConflictError, match="revision 0"):
        preferences.put(alice.id, Preferences(shortcuts={}, revision=0))

    assert preferences.get(alice.id).shortcuts == PLAY_ON_K


def test_shortcuts_saved_as_none_go_back_to_the_pages_defaults(
    preferences: PreferencesService, accounts: AccountService
) -> None:
    alice, _ = _alice_and_bob(accounts)
    preferences.put(alice.id, Preferences(shortcuts=PLAY_ON_K, revision=0))

    saved = preferences.put(alice.id, Preferences(shortcuts=None, revision=1))

    assert saved == Preferences(shortcuts=None, revision=2)


@pytest.mark.parametrize(
    ("shortcuts", "where"),
    [
        ({"toggle": ("Space Bar",)}, "toggle"),
        ({"play pause": ("space",)}, "shortcuts"),
        ({"toggle": ("space",) * 9}, "toggle"),
        ({f"command{n}": ("k",) for n in range(65)}, "shortcuts"),
    ],
    ids=["keys not as the page writes them", "a command name", "too many keys", "too many"],
)
def test_shortcuts_not_as_the_page_writes_them_are_refused(
    preferences: PreferencesService,
    accounts: AccountService,
    shortcuts: dict[str, tuple[str, ...]],
    where: str,
) -> None:
    alice, _ = _alice_and_bob(accounts)

    with pytest.raises(InvalidInputError, match=where):
        preferences.put(alice.id, Preferences(shortcuts=shortcuts, revision=0))
