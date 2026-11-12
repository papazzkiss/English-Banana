"""Server-side account administration. It needs shell access to the server, not an HTTP
session, so it is how the first admin is made (nobody can make themselves admin over the API).

  python -m banana_english.manage set-role <email> admin|teacher|student
  python -m banana_english.manage set-active <email> true|false
  python -m banana_english.manage list [--role admin]

In Docker: docker compose exec api python -m banana_english.manage set-role you@example.com admin
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable

from banana_english.application.use_cases.auth import normalize_email
from banana_english.domain.interfaces.repositories import UnitOfWork
from banana_english.domain.models import Role


def _user_id(uow: UnitOfWork, email: str) -> str:
    account = uow.auth.account_by_email(normalize_email(email))
    if account is None:
        raise SystemExit(f"no account with e-mail {email}")
    return account.user_id


def set_role(uow_factory: Callable[[], UnitOfWork], email: str, role: Role) -> str:
    with uow_factory() as uow:
        user_id = _user_id(uow, email)
        uow.users.set_role(user_id, role)
        uow.users.unlink_all(user_id)
        uow.commit()
    return user_id


def set_active(uow_factory: Callable[[], UnitOfWork], email: str, active: bool) -> str:
    with uow_factory() as uow:
        user_id = _user_id(uow, email)
        uow.users.set_active(user_id, active)
        if not active:
            uow.users.revoke_sessions(user_id)
        uow.commit()
    return user_id


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m banana_english.manage")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("set-role")
    p.add_argument("email")
    p.add_argument("role", choices=[r.value for r in Role])
    p = sub.add_parser("set-active")
    p.add_argument("email")
    p.add_argument("active", choices=["true", "false"])
    p = sub.add_parser("list")
    p.add_argument("--role", choices=[r.value for r in Role])
    args = parser.parse_args(argv)

    from sqlalchemy.orm import sessionmaker

    from banana_english.config.settings import Settings
    from banana_english.infrastructure.database.repositories import (
        SqlUnitOfWork,
        create_db_engine,
    )

    factory = sessionmaker(create_db_engine(Settings().database_url), expire_on_commit=False)

    def uow_factory() -> SqlUnitOfWork:
        return SqlUnitOfWork(factory)

    if args.command == "set-role":
        user_id = set_role(uow_factory, args.email, Role(args.role))
        print(f"{args.email} ({user_id}) is now {args.role}")
    elif args.command == "set-active":
        user_id = set_active(uow_factory, args.email, args.active == "true")
        print(f"{args.email} ({user_id}) active={args.active}")
    else:
        with uow_factory() as uow:
            users, total = uow.users.search(role=Role(args.role) if args.role else None, limit=500)
        for u in users:
            state = "active" if u.user.is_active else "inactive"
            print(f"{u.user.role:<8} {state:<8} {u.email or '-':<40} {u.user.display_name}")
        print(f"{total} user(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
