/** Which screens a role sees. This is only what the menu shows and which pages render: the API
 * checks the role (and which students a teacher may see) on every request, whatever the
 * browser does. */

import type { Role } from "@/lib/types";

export type Area = "admin" | "teacher" | "review";

const AREA_ROLES: Record<Area, readonly Role[]> = {
  admin: ["admin"],
  teacher: ["admin", "teacher"],
  review: ["admin", "teacher"],
};

export function canAccess(role: Role | undefined | null, area: Area): boolean {
  return !!role && AREA_ROLES[area].includes(role);
}

/** The staff area a path belongs to, or null for learner pages (open to every account). */
export function areaForPath(path: string): Area | null {
  for (const area of Object.keys(AREA_ROLES) as Area[]) {
    if (path === `/${area}` || path.startsWith(`/${area}/`)) return area;
  }
  return null;
}

export interface StaffLink { href: string; label: string; area: Area }

const STAFF_LINKS: StaffLink[] = [
  { href: "/admin", label: "Admin dashboard", area: "admin" },
  { href: "/admin/users", label: "Users", area: "admin" },
  { href: "/teacher", label: "Students", area: "teacher" },
  { href: "/review", label: "Question bank", area: "review" },
];

/** The staff links for a role, in menu order (none for students). */
export function staffLinks(role: Role | undefined | null): StaffLink[] {
  return STAFF_LINKS.filter((l) => canAccess(role, l.area));
}

export const ROLE_LABEL: Record<Role, string> = { admin: "Admin", teacher: "Teacher", student: "Student" };
