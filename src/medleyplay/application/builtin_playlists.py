"""The Playlists the server keeps for every Account, such as Favorites.

Making sure they exist is idempotent: it runs as each Account is created and when
the server starts, so a database from before they existed, or one restored from a
copy, gains them too.
"""

import uuid
from datetime import datetime

from sqlalchemy import exists, select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from medleyplay.application.rule_schema import rules_document
from medleyplay.domain.accounts import AccountId
from medleyplay.domain.catalog import FAVORITES_NAME, FAVORITES_RULES, Builtin
from medleyplay.persistence.schema import AccountRow, PlaylistRow


def ensure_builtin_playlists(
    db: Session, now: datetime, account_id: AccountId | None = None
) -> None:
    """Give `account_id`, or every Account, the built-in Playlists it doesn't have yet."""
    missing = select(AccountRow.id).where(
        ~exists().where(
            PlaylistRow.account_id == AccountRow.id,
            PlaylistRow.builtin == Builtin.FAVORITES.value,
        )
    )
    if account_id is not None:
        missing = missing.where(AccountRow.id == account_id)
    for owner in db.scalars(missing).all():
        # A concurrent caller may add it first; the unique index then keeps theirs.
        db.execute(
            insert(PlaylistRow)
            .values(
                id=uuid.uuid4(),
                account_id=owner,
                name=FAVORITES_NAME,
                rules=rules_document(FAVORITES_RULES),
                keep_downloaded=False,
                builtin=Builtin.FAVORITES.value,
                created_at=now,
                updated_at=now,
            )
            .on_conflict_do_nothing()
        )
