"""SQLite storage for the bot suite.

SQLite runs in WAL mode because the Flask app and several WhatsApp
sidecars share this file. WAL lets readers and a writer work at the
same time instead of blocking.
"""

from pathlib import Path

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    """Declarative base for every table in the project."""


def _engine_url():
    """Build the SQLite URL, creating the parent folder if needed."""

    from config import settings

    path = Path(settings.db_path)

    path.parent.mkdir(parents=True, exist_ok=True)

    return f"sqlite:///{path.as_posix()}"


engine = create_engine(
    _engine_url(),
    future=True,
    connect_args={"check_same_thread": False, "timeout": 30},
)


@event.listens_for(engine, "connect")
def _set_sqlite_pragmas(dbapi_connection, connection_record):
    """Apply the pragmas that make concurrent access safe."""

    cursor = dbapi_connection.cursor()

    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA busy_timeout=30000")
    cursor.execute("PRAGMA foreign_keys=ON")

    cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


TENANT_TABLES = (
    "contacts",
    "conversations",
    "messages",
    "alerts",
    "presence_sessions",
)


def _migrate_tenancy():
    """Upgrade an older single-user database in place.

    SQLite cannot change an existing column's uniqueness, so the two
    old global unique indexes are replaced with per-owner ones.
    """

    inspector = inspect(engine)
    existing = set(inspector.get_table_names())

    with engine.begin() as connection:

        for table in TENANT_TABLES:
            if table not in existing:
                continue

            columns = {column["name"] for column in inspector.get_columns(table)}

            if "owner_id" not in columns:
                connection.execute(
                    text(f"ALTER TABLE {table} ADD COLUMN owner_id INTEGER")
                )

        connection.execute(text("DROP INDEX IF EXISTS ix_contacts_jid"))
        connection.execute(text("DROP INDEX IF EXISTS ix_messages_channel_wamid"))

        connection.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ux_contacts_owner_jid "
                "ON contacts(owner_id, jid)"
            )
        )
        connection.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ux_messages_owner_wamid "
                "ON messages(owner_id, channel, wa_message_id)"
            )
        )

        for table in TENANT_TABLES:
            connection.execute(
                text(
                    f"CREATE INDEX IF NOT EXISTS ix_{table}_owner_id "
                    f"ON {table}(owner_id)"
                )
            )


def _migrate_presence_preferences():
    """Add the per-contact session-tracking opt-in to older databases."""

    inspector = inspect(engine)

    if "contact_preferences" not in set(inspector.get_table_names()):
        return

    columns = {
        column["name"]
        for column in inspector.get_columns("contact_preferences")
    }

    if "track_sessions" in columns:
        return

    with engine.begin() as connection:
        connection.execute(
            text(
                "ALTER TABLE contact_preferences "
                "ADD COLUMN track_sessions BOOLEAN NOT NULL DEFAULT 0"
            )
        )


def init_db():
    """Create the schema and upgrade older single-user databases."""

    import models  # noqa: F401  (imported so the tables are registered)

    Base.metadata.create_all(bind=engine)
    _migrate_presence_preferences()
    _migrate_tenancy()

    from services.accounts import bootstrap_admin

    bootstrap_admin()


def session_scope():
    """Return a session. Use as a context manager.

    with session_scope() as session:
        ...
    """

    return SessionLocal()
