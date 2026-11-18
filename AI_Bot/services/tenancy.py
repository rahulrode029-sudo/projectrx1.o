"""Which web account the current work belongs to.

The Flask request sets this once (from the signed-in user, or from a
sidecar token). Every archive query then reads it, so one user can
never stumble into another user's rows.

Outside a request — scripts and tests — the bootstrap admin is used so
the existing memory-service API keeps working. Inside a request there
is deliberately no default: a missing tenant is an error, not a
silent fall back to someone else's data.
"""

from contextlib import contextmanager
from contextvars import ContextVar

from flask import has_request_context

_owner: ContextVar[int | None] = ContextVar("rx_owner_id", default=None)


def set_owner(owner_id: int) -> None:
    """Set the tenant for the current request."""

    _owner.set(int(owner_id))


def clear_owner() -> None:
    """Clear the tenant so one request cannot inherit another's."""

    _owner.set(None)


@contextmanager
def owner_scope(owner_id: int):
    previous = _owner.get()
    _owner.set(int(owner_id))

    try:
        yield
    finally:
        _owner.set(previous)


def current_owner_id() -> int:
    """The active account id, or the admin id outside a web request."""

    value = _owner.get()

    if value is not None:
        return value

    if has_request_context():
        raise RuntimeError(
            "No tenant is set for this request. Check the auth guard."
        )

    from services.accounts import bootstrap_admin_id

    return bootstrap_admin_id()
