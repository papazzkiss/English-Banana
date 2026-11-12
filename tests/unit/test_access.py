"""The role -> permission policy, pinned: a change here must be deliberate."""

from banana_english.domain.models import Role
from banana_english.domain.services.access import ROLE_PERMISSIONS, Permission, can


def test_role_permissions():
    assert {p for p in Permission if can(Role.STUDENT, p)} == {Permission.LEARN}
    assert {p for p in Permission if can(Role.TEACHER, p)} == {
        Permission.LEARN,
        Permission.VIEW_STUDENTS,
        Permission.REVIEW_CONTENT,
    }
    assert all(can(Role.ADMIN, p) for p in Permission)
    assert set(ROLE_PERMISSIONS) == set(Role)
