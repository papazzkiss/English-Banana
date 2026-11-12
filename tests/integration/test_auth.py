"""Accounts, sessions, cookie flow, revocation, expiry, brute-force limit."""

from datetime import timedelta

from banana_english.application.services.passwords import hash_password, verify_password
from banana_english.application.use_cases.auth import token_hash

REG = {
    "email": "Lan@Example.com ",
    "password": "banana-split-9",
    "display_name": "Lan",
    "current_level": "A2",
}


def register(client, **overrides):
    return client.post("/api/v1/auth/register", json={**REG, **overrides})


def test_password_hashing():
    h = hash_password("s3cret-pass")
    assert h.startswith("scrypt$") and "s3cret-pass" not in h
    assert verify_password("s3cret-pass", h) and not verify_password("s3cret-pasS", h)
    assert hash_password("same") != hash_password("same")  # per-password salt
    assert not verify_password("x", "garbage")


def test_register_sets_http_only_cookie_and_web_flow_works(client):
    r = register(client)
    assert r.status_code == 201
    body = r.json()
    assert body["profile"]["display_name"] == "Lan" and body["token"]
    cookie = r.headers["set-cookie"]
    assert "banana_session=" in cookie and "HttpOnly" in cookie and "SameSite=lax" in cookie
    # the browser flow: the cookie alone authenticates
    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200 and me.json()["current_level"] == "A2"
    assert client.get("/api/v1/recommendation/next").status_code == 200


def test_login_logout_and_revocation(client, make_container):
    token = register(client).json()["token"]
    client.cookies.clear()
    bad = client.post("/api/v1/auth/login", json={"email": "lan@example.com", "password": "nope"})
    unknown = client.post("/api/v1/auth/login", json={"email": "who@example.com", "password": "x"})
    assert bad.status_code == unknown.status_code == 401
    assert bad.json()["error"]["message"] == unknown.json()["error"]["message"]  # no enumeration

    login = client.post(
        "/api/v1/auth/login", json={"email": " LAN@example.com", "password": "banana-split-9"}
    )
    assert login.status_code == 200
    h = {"Authorization": f"Bearer {login.json()['token']}"}
    assert client.get("/api/v1/auth/me", headers=h).status_code == 200
    # two independent sessions; logging one out revokes only that one
    assert client.post("/api/v1/auth/logout", headers=h).status_code == 204
    assert client.get("/api/v1/auth/me", headers=h).status_code == 401
    assert (
        client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code
        == 200
    )


def test_token_is_stored_only_as_hash(client):
    token = register(client).json()["token"]
    container = client.app.state.container
    with container.auth._uow_factory() as uow:  # noqa: SLF001 - white-box check
        assert uow.auth.get_session(token) is None
        assert uow.auth.get_session(token_hash(token)) is not None


def test_session_expiry(client, clock):
    token = register(client).json()["token"]
    client.cookies.clear()
    h = {"Authorization": f"Bearer {token}"}
    clock.advance(timedelta(days=31))
    r = client.get("/api/v1/auth/me", headers=h)
    assert r.status_code == 401 and "expired" in r.json()["error"]["message"]


def test_duplicate_email_and_validation(client):
    assert register(client).status_code == 201
    dup = register(client, email="lan@EXAMPLE.com")
    assert dup.status_code == 409
    assert register(client, email="not-an-email").status_code == 422
    assert register(client, email="x@y.co", password="short").status_code == 422


def test_brute_force_limit(client):
    register(client)
    client.cookies.clear()
    codes = [
        client.post(
            "/api/v1/auth/login", json={"email": "lan@example.com", "password": f"wrong{i}"}
        ).status_code
        for i in range(11)
    ]
    assert codes[:10] == [401] * 10 and codes[10] == 429
    # even the right password is refused while locked
    ok = client.post(
        "/api/v1/auth/login", json={"email": "lan@example.com", "password": "banana-split-9"}
    )
    assert ok.status_code == 429
