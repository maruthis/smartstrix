from datetime import timedelta

from app import models
from app.db import SessionLocal
from app.time_utils import utcnow
from .conftest import add_repo


def test_create_list_revoke_token(auth_client):
    client, _org = auth_client

    res = client.post("/api/settings/tokens", json={"name": "CI token"})
    assert res.status_code == 200
    body = res.json()
    assert body["token"].startswith("strix_")
    assert body["token_prefix"] == body["token"][:12]
    assert body["expires_at"] is not None  # defaults to 90 days

    listing = client.get("/api/settings/tokens").json()
    assert len(listing) == 1
    assert "token" not in listing[0]

    revoke = client.request("DELETE", f"/api/settings/tokens/{body['id']}")
    assert revoke.status_code == 200

    listing_after = client.get("/api/settings/tokens").json()
    assert listing_after[0]["status"] == "revoked"


def test_revoke_token_not_found(auth_client):
    client, _org = auth_client
    res = client.request("DELETE", "/api/settings/tokens/does-not-exist")
    assert res.status_code == 404


def test_create_token_with_custom_scopes_and_expiration(auth_client):
    client, _org = auth_client
    res = client.post(
        "/api/settings/tokens",
        json={"name": "Full access", "scopes": ["scans:read", "scans:write", "assets:read"], "expires_in_days": 30},
    )
    body = res.json()
    assert body["scopes"] == ["scans:read", "scans:write", "assets:read"]
    assert body["expires_at"] is not None


def test_create_token_with_no_expiration(auth_client):
    client, _org = auth_client
    res = client.post("/api/settings/tokens", json={"name": "Long-lived", "expires_in_days": None})
    assert res.json()["expires_at"] is None


def test_create_and_revoke_token_require_admin(auth_client):
    from .conftest import add_member

    client, org = auth_client
    admin_token = client.post("/api/settings/tokens", json={"name": "Admin token"}).json()

    add_member(client, org)
    create = client.post("/api/settings/tokens", json={"name": "Member token"})
    assert create.status_code == 403
    assert create.json()["detail"] == "admin_required"

    revoke = client.request("DELETE", f"/api/settings/tokens/{admin_token['id']}")
    assert revoke.status_code == 403
    assert revoke.json()["detail"] == "admin_required"

    # A member can still see the list.
    assert client.get("/api/settings/tokens").status_code == 200


def test_api_token_can_read_and_start_scans_without_session_cookies(auth_client):
    client, _org = auth_client
    repo = add_repo(client)
    token = client.post(
        "/api/settings/tokens",
        json={"name": "CI", "scopes": ["scans:read", "scans:write"], "expires_in_days": 30},
    ).json()["token"]

    client.cookies.clear()
    client.headers.pop("x-csrf-token", None)

    read = client.get("/api/pentests", headers={"authorization": f"Bearer {token}"})
    assert read.status_code == 200

    create = client.post(
        "/api/pentests",
        headers={"authorization": f"Bearer {token}"},
        json={"target_type": "repository", "target_id": repo["id"]},
    )
    assert create.status_code == 200, create.text
    assert create.json()["created_at"]

    listing = client.get("/api/settings/tokens", headers={"authorization": f"Bearer {token}"})
    assert listing.status_code == 403

    db = SessionLocal()
    try:
        row = db.query(models.ApiToken).filter_by(token_prefix=token[:12]).one()
        assert row.last_used_at is not None
    finally:
        db.close()


def test_api_token_rejects_insufficient_revoked_and_expired_tokens(auth_client):
    client, _org = auth_client
    read_only = client.post("/api/settings/tokens", json={"name": "Read only", "scopes": ["scans:read"]}).json()
    expiring = client.post("/api/settings/tokens", json={"name": "Expired", "scopes": ["scans:read"]}).json()
    revoked = client.post("/api/settings/tokens", json={"name": "Revoked", "scopes": ["scans:read"]}).json()
    client.request("DELETE", f"/api/settings/tokens/{revoked['id']}")

    db = SessionLocal()
    try:
        row = db.get(models.ApiToken, expiring["id"])
        row.expires_at = utcnow() - timedelta(seconds=1)
        db.commit()
    finally:
        db.close()

    client.cookies.clear()
    client.headers.pop("x-csrf-token", None)

    assert client.post("/api/pentests", headers={"authorization": f"Bearer {read_only['token']}"}, json={}).status_code == 403
    assert client.get("/api/pentests", headers={"authorization": f"Bearer {revoked['token']}"}).status_code == 401
    assert client.get("/api/pentests", headers={"authorization": f"Bearer {expiring['token']}"}).status_code == 401
