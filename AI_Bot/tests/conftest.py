"""Shared test setup.

The environment is set before anything imports `config`, so the tests
use a throwaway database and never touch the real one.
"""

import os
import tempfile
import uuid

os.environ.setdefault(
    "DB_PATH",
    os.path.join(tempfile.mkdtemp(prefix="aibot-test-"), "test.db"),
)

os.environ.setdefault("WA_SHARED_SECRET", "test-shared-secret")

os.environ.setdefault("Gemini_API_KEY", "test-key")

os.environ.setdefault("WEB_PASSWORD", "test-password")
os.environ.setdefault("ADMIN_USERNAME", "admin")
os.environ.setdefault("ADMIN_PASSWORD", "test-password")
os.environ.setdefault("ADMIN_PHONE", "919423031182")
os.environ.setdefault("FLASK_SECRET_KEY", "test-secret-key-for-tests")

import pytest


@pytest.fixture(scope="session", autouse=True)
def _database():
    """Create the schema once for the whole test session."""

    from database.database import init_db

    init_db()

    yield


@pytest.fixture(autouse=True)
def _tenant():
    """Direct service calls in tests use the admin account."""

    from services import accounts
    from services.tenancy import owner_scope

    with owner_scope(accounts.bootstrap_admin_id()):
        yield


@pytest.fixture
def session():
    """A database session that is rolled back after each test."""

    from database.database import session_scope

    with session_scope() as db:
        yield db
        db.rollback()


@pytest.fixture
def anon_client():
    """A Flask test client that is not logged in."""

    from app import app

    app.config.update(TESTING=True)

    with app.test_client() as test_client:
        yield test_client


@pytest.fixture
def client(anon_client):
    """A Flask test client, logged in as the admin by default."""

    return _login(anon_client, "admin", os.environ["ADMIN_PASSWORD"])


@pytest.fixture
def admin_client(client):
    """Explicit alias for the admin client."""

    return client


def _login(test_client, username, password):
    response = test_client.post(
        "/login",
        data={"username": username, "password": password},
        follow_redirects=False,
    )

    assert response.status_code == 302, "test login failed"

    # The test client keeps its request context, which would otherwise
    # leave the tenant cleared for direct service calls in the test.
    from services import accounts
    from services.tenancy import set_owner

    user = accounts.find_by_username(username)
    set_owner(user.id)

    return test_client


@pytest.fixture
def other_client():
    """A second account, used to prove data isolation."""

    from app import app
    from services import accounts

    suffix = uuid.uuid4().hex[:8]
    username = f"user_{suffix}"
    phone = "9" + str(uuid.uuid4().int % 10**9).zfill(9)
    password = "other-password-123"

    user = accounts.create_user(username, password, "Other User", phone)

    app.config.update(TESTING=True)

    # No `with` here: a preserved request context from a second client
    # would clash with the main client's context stack.
    test_client = app.test_client()

    yield _login(test_client, username, password), user


@pytest.fixture
def auth_headers():
    """Headers that pass the sidecar's shared secret check."""

    from config import settings

    return {"X-WA-Secret": settings.wa_shared_secret}
