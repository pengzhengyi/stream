"""Alembic's entry point: runs migrations on the connection `migrate` hands it."""

from alembic import context
from sqlalchemy import Connection

from medleyplay.persistence.schema import Base

connection = context.config.attributes.get("connection")
if not isinstance(connection, Connection):
    message = "Run migrations through medleyplay.persistence.database.migrate."
    raise TypeError(message)

# SQLite can't alter most constraints in place; batch mode rebuilds the table instead.
context.configure(
    connection=connection,
    target_metadata=Base.metadata,
    render_as_batch=True,
)
with context.begin_transaction():
    context.run_migrations()
