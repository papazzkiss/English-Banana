"""Accounts and sessions.

* Passwords: scrypt with a per-password salt (application/services/passwords.py).
* Sessions: 256-bit random bearer tokens. Only their SHA-256 is stored, so a leaked database
  does not leak usable sessions; logout deletes the row (revocation).
* Login failures return one generic message for "unknown e-mail" and "wrong password", cost the
  same scrypt time either way, and are rate-limited per e-mail (in-process; single-host scope).
* Every request resolves its token to a Principal (user id + role) with one query that also
  reads the account status: a disabled account is refused even with a live session, and a role
  change applies to the next request. The role never comes from the request.
"""

from __future__ import annotations

import hashlib
import re
import secrets
import threading
import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import timedelta

from banana_english.application.services.passwords import (
    DUMMY_HASH,
    hash_password,
    verify_password,
)
from banana_english.application.use_cases.common import (
    AccountDisabledError,
    ConflictError,
    InvalidInputError,
    TooManyAttemptsError,
    UnauthorizedError,
    UowFactory,
)
from banana_english.application.use_cases.learner import LearnerOverview
from banana_english.domain.interfaces.infra import Clock
from banana_english.domain.models import (
    Account,
    AuthSession,
    CefrLevel,
    LearnerProfile,
    Principal,
    User,
)

EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}$")
MIN_PASSWORD = 8
MAX_FAILURES = 10
FAILURE_WINDOW_SECONDS = 15 * 60


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def normalize_email(email: str) -> str:
    return email.strip().lower()


@dataclass(frozen=True)
class SignedIn:
    overview: LearnerOverview
    token: str
    expires_in_seconds: int


class LoginLimiter:
    def __init__(
        self, max_failures: int = MAX_FAILURES, window_seconds: int = FAILURE_WINDOW_SECONDS
    ) -> None:
        self._max = max_failures
        self._window = window_seconds
        self._failures: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str) -> None:
        with self._lock:
            q = self._failures[key]
            while q and q[0] < time.monotonic() - self._window:
                q.popleft()
            if len(q) >= self._max:
                raise TooManyAttemptsError("too many failed logins; try again later")

    def fail(self, key: str) -> None:
        with self._lock:
            self._failures[key].append(time.monotonic())

    def reset(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)


class Auth:
    def __init__(
        self,
        uow_factory: UowFactory,
        clock: Clock,
        session_days: int = 30,
        limiter: LoginLimiter | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._clock = clock
        self._ttl = timedelta(days=session_days)
        self._limiter = limiter or LoginLimiter()

    def _new_session(self, uow, user_id: str) -> str:
        token = secrets.token_urlsafe(32)
        now = self._clock.now()
        uow.auth.add_session(AuthSession(token_hash(token), user_id, now, now + self._ttl))
        return token

    def register(
        self,
        email: str,
        password: str,
        display_name: str,
        current_level: CefrLevel,
        target_level: CefrLevel,
        native_language: str | None,
    ) -> SignedIn:
        email = normalize_email(email)
        if not EMAIL.match(email):
            raise InvalidInputError("please enter a valid e-mail address")
        if len(password) < MIN_PASSWORD:
            raise InvalidInputError(f"password must have at least {MIN_PASSWORD} characters")
        password_hash = hash_password(password)  # outside the transaction: ~50 ms of CPU
        now = self._clock.now()
        user = User(str(uuid.uuid4()), display_name.strip(), now)
        profile = LearnerProfile(user.id, current_level, target_level, native_language, now)
        with self._uow_factory() as uow:
            if uow.auth.account_by_email(email):
                raise ConflictError("an account with this e-mail already exists")
            uow.learners.add(user, profile)
            uow.auth.add_account(Account(user.id, email, password_hash, now))
            token = self._new_session(uow, user.id)
            uow.commit()
        return SignedIn(LearnerOverview(user, profile, 0, 0), token, int(self._ttl.total_seconds()))

    def login(self, email: str, password: str) -> SignedIn:
        email = normalize_email(email)
        self._limiter.check(email)
        with self._uow_factory() as uow:
            account = uow.auth.account_by_email(email)
        # Always pay the scrypt cost, so response time does not reveal unknown e-mails.
        ok = verify_password(password, account.password_hash if account else DUMMY_HASH)
        if not (account and ok):
            self._limiter.fail(email)
            raise UnauthorizedError("wrong e-mail or password")
        self._limiter.reset(email)
        with self._uow_factory() as uow:
            found = uow.learners.get(account.user_id)
            if found is not None and not found[0].is_active:  # right password, but disabled
                raise AccountDisabledError("this account is disabled; contact an administrator")
            token = self._new_session(uow, account.user_id)
            total, correct = uow.attempts.count(account.user_id)
            uow.commit()
        return SignedIn(
            LearnerOverview(found[0], found[1], total, correct),
            token,
            int(self._ttl.total_seconds()),
        )

    def principal(self, token: str) -> Principal:
        """The user behind a valid, unexpired session of an active account."""
        with self._uow_factory() as uow:
            found = uow.auth.session_user(token_hash(token))
            if found is None:
                raise UnauthorizedError("please sign in")
            session, user = found
            if session.expires_at <= self._clock.now():
                uow.auth.delete_session(session.token_hash)
                uow.commit()
                raise UnauthorizedError("your session has expired, please sign in again")
        if not user.is_active:
            raise AccountDisabledError("this account is disabled; contact an administrator")
        return Principal(user.id, user.role)

    def authenticate(self, token: str) -> str:
        """Return the learner id for a valid, unexpired session token."""
        return self.principal(token).user_id

    def logout(self, token: str) -> None:
        with self._uow_factory() as uow:
            uow.auth.delete_session(token_hash(token))
            uow.commit()
