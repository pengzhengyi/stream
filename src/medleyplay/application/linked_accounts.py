"""Linked accounts: saving an Account's login on a site, and lending a copy to its Jobs.

The login lives in the Keychain and the catalog keeps its state. The Keychain is
written first and the row second, so a crash between them leaves only a secret
with no row, which the next save replaces.
"""

import dataclasses
import threading
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime

from pydantic import ValidationError
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session, sessionmaker

from medleyplay.application import Clock
from medleyplay.application.plugins import PluginService
from medleyplay.application.secrets import Secrets
from medleyplay.domain.accounts import Account, AccountId
from medleyplay.domain.errors import InvalidInputError, NotFoundError
from medleyplay.domain.linked_accounts import LinkedAccount, LinkState, check_site, secret_name
from medleyplay.persistence.schema import LinkedAccountRow
from medleyplay.plugin_api import CHECK_LOGIN, CREDENTIAL_SPEC, CheckLogin


@dataclass(frozen=True)
class LentLogin:
    """A copy of a valid login for one Job, and the revision it was copied at."""

    text: str
    revision: int


class LinkedAccountService:
    """Save, list, and remove linked accounts, and lend their logins to Jobs."""

    def __init__(
        self, units: sessionmaker[Session], clock: Clock, plugins: PluginService, secrets: Secrets
    ) -> None:
        """Create a service keeping logins in `secrets`."""
        self._units = units
        self._clock = clock
        self._plugins = plugins
        self._secrets = secrets
        self._locks: defaultdict[tuple[AccountId, str], threading.Lock] = defaultdict(
            threading.Lock
        )

    def list_linked(self, caller: Account) -> list[LinkedAccount]:
        """Return the caller's linked accounts, by site, as they stand now."""
        now = self._clock()
        with self._units() as db:
            rows = db.scalars(
                select(LinkedAccountRow)
                .where(LinkedAccountRow.account_id == caller.id)
                .order_by(LinkedAccountRow.site)
            ).all()
            return [_current(_to_linked(row), now) for row in rows]

    def save(self, caller: Account, site: str, text: str) -> LinkedAccount:
        """Save the caller's login on `site` from pasted text, such as a cookies file.

        The site's plugin keeps what it needs; text holding no login is refused.
        """
        site = check_site(site)
        if site not in self._plugins.available_keys().get(CREDENTIAL_SPEC.name, []):
            message = f"No plugin that is on reads logins for {site!r}."
            raise NotFoundError(message)
        try:
            request = CheckLogin(text=text)
        except ValidationError:
            message = "The pasted login is too long; export only the site's cookies."
            raise InvalidInputError(message) from None
        checked = self._plugins.call(CHECK_LOGIN, site, request)
        if not checked.valid:
            raise InvalidInputError(checked.message or "The pasted text holds no login.")
        with self._locks[caller.id, site]:
            self._secrets.set(secret_name(caller.id, site), checked.login)
            with self._units.begin() as db:
                row = db.get(LinkedAccountRow, (caller.id, site))
                if row is None:
                    row = LinkedAccountRow(account_id=caller.id, site=site, revision=0)
                    db.add(row)
                row.state = LinkState.VALID
                row.expires_at = checked.expires_at
                row.saved_at = self._clock()
                row.revision += 1
                db.flush()
                return _to_linked(row)

    def remove(self, caller: Account, site: str) -> None:
        """Forget the caller's login on `site`; forgetting one that isn't there is fine."""
        self.forget(caller.id, check_site(site))

    def forget(self, account_id: AccountId, site: str | None = None) -> None:
        """Forget an Account's login on `site`, or on every site, as when it is deleted.

        Every site means each the catalog knows of and each a plugin reads logins
        for, so a login is forgotten even after its row went with its Account.
        """
        with self._units() as db:
            query = select(LinkedAccountRow.site).where(LinkedAccountRow.account_id == account_id)
            known = set(db.scalars(query))
        readable = set(self._plugins.available_keys().get(CREDENTIAL_SPEC.name, []))
        sites = {site} if site is not None else known | readable
        for each in sorted(sites):
            with self._locks[account_id, each]:
                self._secrets.delete(secret_name(account_id, each))
                with self._units.begin() as db:
                    db.execute(
                        delete(LinkedAccountRow).where(
                            LinkedAccountRow.account_id == account_id,
                            LinkedAccountRow.site == each,
                        )
                    )

    def has_valid(self, account_id: AccountId, site: str) -> bool:
        """Return whether the Account has a valid login on `site` now."""
        with self._units() as db:
            row = db.get(LinkedAccountRow, (account_id, site))
            if row is None:
                return False
            return _current(_to_linked(row), self._clock()).state is LinkState.VALID

    def lend(self, account_id: AccountId, site: str) -> LentLogin | None:
        """Return a copy of the Account's valid login on `site` for a Job, or `None`.

        A login the Keychain no longer holds needs sign-in from then on.
        """
        with self._units() as db:
            row = db.get(LinkedAccountRow, (account_id, site))
            if row is None:
                return None
            linked = _current(_to_linked(row), self._clock())
        if linked.state is not LinkState.VALID:
            return None
        text = self._secrets.get(secret_name(account_id, site))
        if text is None:
            self.refused(account_id, site, linked.revision)
            return None
        return LentLogin(text, linked.revision)

    def refused(self, account_id: AccountId, site: str, revision: int) -> None:
        """Mark the login *needs sign-in*, unless it was saved again since `revision`."""
        with self._units.begin() as db:
            db.execute(
                update(LinkedAccountRow)
                .where(
                    LinkedAccountRow.account_id == account_id,
                    LinkedAccountRow.site == site,
                    LinkedAccountRow.revision == revision,
                )
                .values(state=LinkState.NEEDS_SIGN_IN)
            )


def _to_linked(row: LinkedAccountRow) -> LinkedAccount:
    return LinkedAccount(
        site=row.site,
        state=LinkState(row.state),
        expires_at=row.expires_at,
        saved_at=row.saved_at,
        revision=row.revision,
    )


def _current(linked: LinkedAccount, now: datetime) -> LinkedAccount:
    return dataclasses.replace(linked, state=linked.state_at(now))
