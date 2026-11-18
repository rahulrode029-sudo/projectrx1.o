"""Password hashing.

Only hashes are ever stored. The forgot-password flow never reveals an
old password — it sends a one-time link so the user can set a new one.
"""

from werkzeug.security import check_password_hash, generate_password_hash


def hash_password(password: str) -> str:
    return generate_password_hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    if not password or not password_hash:
        return False

    try:
        return check_password_hash(password_hash, password)
    except (TypeError, ValueError):
        return False
