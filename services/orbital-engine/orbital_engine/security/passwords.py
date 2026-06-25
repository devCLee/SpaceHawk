"""Password hashing (bcrypt).

Credentials are stored only as bcrypt hashes (``app_user.password_hash``); the
plaintext is never persisted or logged. bcrypt ignores input beyond 72 bytes, so
over-long passwords are truncated to that boundary before hashing/verification to
keep both sides consistent.
"""

from __future__ import annotations

import bcrypt

_BCRYPT_MAX_BYTES = 72


def _encode(password: str) -> bytes:
    return password.encode("utf-8")[:_BCRYPT_MAX_BYTES]


def hash_password(password: str) -> str:
    """Return a bcrypt hash (cost 12) of ``password``."""
    return bcrypt.hashpw(_encode(password), bcrypt.gensalt(rounds=12)).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    """True iff ``password`` matches ``password_hash``. Never raises on bad input."""
    try:
        return bcrypt.checkpw(_encode(password), password_hash.encode("ascii"))
    except (ValueError, TypeError):
        return False
