# Access control

Three roles, stored on the user and read from the database on every request. A role never
comes from a request body, a header or the browser.

| Role | What it adds |
|---|---|
| `student` | Learn: every practice module, the question bank, AI Monkey, voice, their own progress and history. Every new account is a student. |
| `teacher` | Everything a student can do, plus: the progress and results of the students an admin assigned to them, and question-bank review (approve / disable questions). |
| `admin` | Everything, plus: users (list, search, role, activate / deactivate, teacher-student links), platform statistics and the configuration summary. |

There is no guest role: without a session only public content lists (grammar topics and
exercises, listening lessons, speaking prompts, scenarios, all without answers), `/health`,
`/api/v1/health` (`{"status": "ok"}` only) and `/api/v1/features` answer.

## How a request is checked

```
token (httpOnly cookie or Bearer)
  → session row + user row, one query (SHA-256 of the token; expiry)
  → account active?                              no → 403 account_disabled
  → role holds the permission for this router?   no → 403 forbidden
  → the use case checks the permission again, and ownership
```

- `api/deps.py`: `current_principal` resolves the token to a `Principal(user_id, role)` once
  per request. `LearnerId` (every learning endpoint) is derived from it, so learning endpoints
  only ever read and write the signed-in user's own data: none of them takes a user id.
- `require(permission)` guards whole routers (`/admin/*`, `/teacher/*`) and the review
  endpoints of `/bank/*`.
- `domain/services/access.py` holds the role → permission map (`learn`, `view_students`,
  `review_content`, `manage_users`, `view_system`). No permission tables: three fixed roles do
  not need them.
- Use cases (`application/use_cases/admin.py`, `teacher.py`, `question_bank.py`) check the
  permission themselves too, so a route that forgets its dependency is still safe.

## Endpoints

| Endpoints | student | teacher | admin | Ownership |
|---|---|---|---|---|
| `/auth/register`, `/auth/login`, `/auth/logout` | public | public | public | Register rejects unknown fields (a `role` in the body is a 422); a disabled account cannot log in (403 after a correct password only) |
| `/auth/me`, `/learner/*`, `/recommendation/next` | ✓ | ✓ | ✓ | The signed-in user only (no id in the path) |
| `/vocabulary/*`, `/grammar/attempt`, `/listening/attempt`, `/speaking/attempt` | ✓ | ✓ | ✓ | Recorded for the signed-in user |
| `/conversations/{id}/*`, `/jobs/{id}`, `/tutor/explain` | ✓ | ✓ | ✓ | Owner only; another user's id answers 404 (not even existence leaks) |
| `/listening/lessons/{id}/transcript` | ✓ | ✓ | ✓ | 409 until the user answered every question |
| `/monkey/*` | ✓ | ✓ | ✓ | Nothing stored server-side |
| `/bank/{skill}/facets`, `/sets`, `/summary`, `POST /bank/answer` | ✓ | ✓ | ✓ | The user's own history; draft and disabled questions are never served nor answerable |
| `/bank/passages/{id}/transcript` | ✓ | ✓ | ✓ | 409 until the user answered a question about it (it holds dictation answers) |
| `GET /bank/{skill}/review`, `PATCH /bank/questions/{id}` | 403 | ✓ | ✓ | The decision records who and when |
| `GET /teacher/students`, `/teacher/students/{id}/progress`, `/attempts` | 403 | assigned students | all | 403 for a student not assigned to the teacher |
| `/admin/users*`, `/admin/stats` | 403 | 403 | ✓ | An admin cannot change their own role or status; the last active admin cannot be demoted or disabled |
| `GET /api/v1/health` | status only | status only | + configuration | |
| `/metrics`, `/docs`, `/openapi.json` | not proxied: only on the API port (localhost) | | | |

## Accounts

- **The first admin** is made on the server (it needs shell access, not a session):
  `docker compose exec api python -m banana_english.manage set-role you@example.com admin`.
  Also `set-active <email> true|false` and `list [--role admin]`.
- **Deactivate, never delete.** A disabled account keeps its history; its sessions are
  deleted at once, and any session left (for example a change made directly in the database)
  is refused on its next request, because the status is read with the session.
- **Role changes** apply on the next request. Changing a role removes the user's
  teacher-student links (they belonged to the old role).
- **Teacher scope**: an admin links a teacher to students (Users → a teacher → Add a student,
  or `PUT /admin/users/{teacher}/students/{student}`). A teacher sees nobody else.

## Frontend

The menu shows staff links by role (`lib/access.ts`), and `components/RoleGate.tsx` renders a
"no access" page when someone opens `/admin`, `/admin/users`, `/teacher` or `/review` without
the role. This is only presentation: the API refuses those calls anyway.

## Database (migration 0004)

Additive only: `users.role` (default `student`, indexed), `users.is_active` (default true),
table `teacher_students (teacher_id, student_id, created_at)` indexed both ways, and
`bank_questions.reviewed_by / reviewed_at`. Every existing user became an active student;
accounts, sessions and progress were not touched.

## Cost

One query per request resolves the session, the role and the status (it was already one
query for the session). No extra query on the answer path of the question bank.
