from .conftest import otp_login


def test_list_members_includes_creator(auth_client):
    client, _org = auth_client
    res = client.get("/api/members")
    assert res.status_code == 200
    members = res.json()
    assert len(members) == 1
    assert members[0]["role"] == "admin"


def test_invite_list_accept_flow(auth_client):
    client, org = auth_client

    invite = client.post("/api/members/invitations", json={"email": "teammate@example.com", "role": "member"})
    assert invite.status_code == 200
    token = invite.json()["dev_accept_token"]

    pending = client.get("/api/members/invitations")
    assert len(pending.json()) == 1

    otp_login(client, "teammate@example.com")
    accept = client.post("/api/members/invitations/accept", json={"token": token})
    assert accept.status_code == 200
    assert accept.json()["role"] == "member"

    client.post("/api/auth/switch-org", json={"org_id": org["id"]})
    members = client.get("/api/members").json()
    assert len(members) == 2


def test_invite_rejects_existing_member(auth_client):
    client, _org = auth_client
    res = client.post("/api/members/invitations", json={"email": "user@example.com", "role": "member"})
    assert res.status_code == 409
    assert res.json()["detail"] == "already_a_member"


def test_invite_requires_admin(auth_client):
    client, org = auth_client
    invite = client.post("/api/members/invitations", json={"email": "plain@example.com", "role": "member"})
    token = invite.json()["dev_accept_token"]

    otp_login(client, "plain@example.com")
    client.post("/api/members/invitations/accept", json={"token": token})
    client.post("/api/auth/switch-org", json={"org_id": org["id"]})

    res = client.post("/api/members/invitations", json={"email": "another@example.com", "role": "member"})
    assert res.status_code == 403
    assert res.json()["detail"] == "admin_required"


def test_accept_invitation_wrong_email_rejected(auth_client):
    client, _org = auth_client
    invite = client.post("/api/members/invitations", json={"email": "intended@example.com", "role": "member"})
    token = invite.json()["dev_accept_token"]

    otp_login(client, "someone-else@example.com")
    res = client.post("/api/members/invitations/accept", json={"token": token})
    assert res.status_code == 403
    assert res.json()["detail"] == "invitation_email_mismatch"


def test_accept_invalid_token_rejected(auth_client):
    client, _org = auth_client
    res = client.post("/api/members/invitations/accept", json={"token": "not-a-real-token"})
    assert res.status_code == 404


def test_revoke_invitation(auth_client):
    client, _org = auth_client
    invite = client.post("/api/members/invitations", json={"email": "gone@example.com", "role": "member"})
    invite_id = invite.json()["invitation_id"]

    res = client.post(f"/api/members/invitations/{invite_id}/revoke")
    assert res.status_code == 200
    assert client.get("/api/members/invitations").json() == []


def test_revoke_invitation_not_found(auth_client):
    client, _org = auth_client
    res = client.post("/api/members/invitations/does-not-exist/revoke")
    assert res.status_code == 404


def test_update_role_and_remove_member(auth_client):
    client, org = auth_client
    invite = client.post("/api/members/invitations", json={"email": "member2@example.com", "role": "member"})
    token = invite.json()["dev_accept_token"]

    otp_login(client, "member2@example.com")
    client.post("/api/members/invitations/accept", json={"token": token})
    member2_id = client.get("/api/auth/me").json()["user"]["id"]

    otp_login(client, "user@example.com")
    client.post("/api/auth/switch-org", json={"org_id": org["id"]})

    promote = client.patch(f"/api/members/{member2_id}", json={"role": "admin"})
    assert promote.status_code == 200
    assert promote.json()["role"] == "admin"

    remove = client.request("DELETE", f"/api/members/{member2_id}")
    assert remove.status_code == 200
    assert len(client.get("/api/members").json()) == 1


def test_update_role_not_found(auth_client):
    client, _org = auth_client
    res = client.patch("/api/members/does-not-exist", json={"role": "admin"})
    assert res.status_code == 404


def test_remove_member_not_found(auth_client):
    client, _org = auth_client
    res = client.request("DELETE", "/api/members/does-not-exist")
    assert res.status_code == 404


def test_dev_accept_token_hidden_outside_dev_mode(auth_client, monkeypatch):
    from app.routers import members as members_module

    client, _org = auth_client
    monkeypatch.setattr(members_module.settings, "dev_mode", False)

    res = client.post("/api/members/invitations", json={"email": "teammate@example.com", "role": "member"})
    assert res.status_code == 200
    body = res.json()
    assert "dev_accept_token" not in body
    assert body["invitation_id"]


def test_expired_invitation_rejected(auth_client):
    from datetime import timedelta

    from app import models
    from app.db import SessionLocal
    from app.time_utils import utcnow

    client, _org = auth_client
    invite = client.post("/api/members/invitations", json={"email": "late@example.com", "role": "member"})
    token = invite.json()["dev_accept_token"]

    db = SessionLocal()
    try:
        row = db.query(models.Invitation).filter_by(token=token).first()
        row.expires_at = utcnow() - timedelta(days=1)
        db.commit()
    finally:
        db.close()

    otp_login(client, "late@example.com")
    res = client.post("/api/members/invitations/accept", json={"token": token})
    assert res.status_code == 410
    assert res.json()["detail"] == "invitation_expired"
