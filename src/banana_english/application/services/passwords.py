"""Password hashing with scrypt (stdlib, memory-hard). Format: scrypt$n$r$p$salt$hash (base64)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

N, R, P, DKLEN = 2**14, 8, 1, 32


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=N, r=R, p=P, dklen=DKLEN)
    enc = base64.b64encode
    return f"scrypt${N}${R}${P}${enc(salt).decode()}${enc(digest).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
        if scheme != "scrypt":
            return False
        expected = base64.b64decode(digest)
        actual = hashlib.scrypt(
            password.encode(),
            salt=base64.b64decode(salt),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(expected),
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


# Used when the e-mail is unknown, so a failed login costs the same time either way.
DUMMY_HASH = hash_password(secrets.token_urlsafe(16))
