"""Who may do what. Three fixed roles, so a static map instead of permission tables.

Every signed-in account can learn (a teacher or an admin can practise too). What changes with
the role is access to other people's data and to the platform:

| Permission      | student | teacher               | admin |
|-----------------|---------|-----------------------|-------|
| learn           | yes     | yes                   | yes   |
| view_students   | -       | assigned students     | all   |
| review_content  | -       | yes                   | yes   |
| manage_users    | -       | -                     | yes   |
| view_system     | -       | -                     | yes   |

Ownership ("which students") is checked in the use cases, not here.
"""

from __future__ import annotations

from enum import StrEnum

from banana_english.domain.models.enums import Role


class Permission(StrEnum):
    LEARN = "learn"
    VIEW_STUDENTS = "view_students"
    REVIEW_CONTENT = "review_content"
    MANAGE_USERS = "manage_users"
    VIEW_SYSTEM = "view_system"


ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.STUDENT: frozenset({Permission.LEARN}),
    Role.TEACHER: frozenset(
        {Permission.LEARN, Permission.VIEW_STUDENTS, Permission.REVIEW_CONTENT}
    ),
    Role.ADMIN: frozenset(Permission),
}


def can(role: Role, permission: Permission) -> bool:
    return permission in ROLE_PERMISSIONS.get(role, frozenset())
