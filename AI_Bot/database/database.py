"""SQLite storage for the bot suite.

SQLite runs in WAL mode because three processes share this file:
the Flask app, the Telegram bot and the WhatsApp sidecar. WAL lets
readers and a writer work at the same time instead of blocking.
"""

from pathlib import Path

from sqlalchemy import create_engine, event
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


def init_db():
    """Create any table that does not exist yet."""

    import models  # noqa: F401  (imported so the tables are registered)

    Base.metadata.create_all(bind=engine)


def session_scope():
    """Return a session. Use as a context manager.

    with session_scope() as session:
        ...
    """

    return SessionLocal()
