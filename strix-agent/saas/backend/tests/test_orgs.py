from .conftest import create_org, otp_login


def test_create_org_makes_creator_admin(client):
    otp_login(client)
    org = create_org(client, "Acme")
    me = client.get("/api/auth/me").json()
    assert me["active_org"]["name"] == "Acme"
    assert me["role"] == "admin"


def test_get_current_org(auth_client):
    client, org = auth_client
    res = client.get("/api/orgs/current")
    assert res.status_code == 200
    assert res.json()["id"] == org["id"]


def test_rename_org(auth_client):
    client, _org = auth_client
    res = client.patch("/api/orgs/current", json={"name": "New Name"})
    assert res.status_code == 200
    assert res.json()["name"] == "New Name"


def test_rename_org_blank_name_keeps_existing(auth_client):
    client, org = auth_client
    res = client.patch("/api/orgs/current", json={"name": "   "})
    assert res.status_code == 200
    assert res.json()["name"] == org["name"]


def test_rename_org_requires_admin(client):
    otp_login(client, "member@example.com")
    org = create_org(client, "Acme")

    # Second user joins as a plain member via a real invite/accept round-trip.
    otp_login(client, "admin@example.com")
    create_org(client, "Other Org")  # unrelated org owned by this user

    # Re-login as the first admin to invite the second user into "Acme".
    otp_login(client, "member@example.com")
    client.post("/api/auth/switch-org", json={"org_id": org["id"]})
    invite = client.post("/api/members/invitations", json={"email": "admin@example.com", "role": "member"})
    token = invite.json()["dev_accept_token"]

    otp_login(client, "admin@example.com")
    client.post("/api/members/invitations/accept", json={"token": token})
    client.post("/api/auth/switch-org", json={"org_id": org["id"]})

    res = client.patch("/api/orgs/current", json={"name": "Hacked"})
    assert res.status_code == 403
    assert res.json()["detail"] == "admin_required"


def test_delete_org_requires_matching_name(auth_client):
    client, org = auth_client
    res = client.request("DELETE", "/api/orgs/current", json={"confirm_name": "wrong"})
    assert res.status_code == 400
    assert res.json()["detail"] == "name_confirmation_mismatch"

    res = client.request("DELETE", "/api/orgs/current", json={"confirm_name": org["name"]})
    assert res.status_code == 200
    assert res.json()["ok"] is True

    me = client.get("/api/auth/me").json()
    assert me["active_org"] is None


def test_create_org_sets_active_org_without_explicit_switch(client):
    """Regression test: POST /api/orgs must leave the session pointed at
    the new org even if the caller never calls /api/auth/switch-org
    afterward (conftest's create_org() helper always does call it, which
    would otherwise mask this)."""
    otp_login(client)
    res = client.post("/api/orgs", json={"name": "No Explicit Switch Co"})
    assert res.status_code == 200
    org = res.json()

    me = client.get("/api/auth/me").json()
    assert me["active_org"]["id"] == org["id"]

    # An org-scoped endpoint works immediately, with no switch-org call.
    assert client.get("/api/repositories").status_code == 200
