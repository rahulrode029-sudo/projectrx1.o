"""Shared test setup.

The environment is set before anything imports `config`, so the tests
use a throwaway database and never touch the real one.
"""

import os
import tempfile

os.environ.setdefault(
    "DB_PATH",
    os.path.join(tempfile.mkdtemp(prefix="aibot-test-"), "test.db"),
)

os.environ.setdefault("WA_SHARED_SECRET", "test-shared-secret")

os.environ.setdefault("Gemini_API_KEY", "test-key")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")
os.environ.setdefault("TMDB_API_KEY", "test-key")

import pytest


@pytest.fixture(scope="session", autouse=True)
def _database():
    """Create the schema once for the whole test session."""

    from database.database import init_db

    init_db()

    yield


@pytest.fixture
def session():
    """A database session that is rolled back after each test."""

    from database.database import session_scope

    with session_scope() as db:
        yield db
        db.rollback()


@pytest.fixture
def client():
    """A Flask test client."""

    from app import app

    app.config.update(TESTING=True)

    with app.test_client() as test_client:
        yield test_client


@pytest.fixture
def auth_headers():
    """Headers that pass the sidecar's shared secret check."""

    from config import settings

    return {"X-WA-Secret": settings.wa_shared_secret}
