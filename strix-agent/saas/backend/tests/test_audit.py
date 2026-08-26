def test_audit_log_records_actions(auth_client):
    client, org = auth_client

    client.patch("/api/orgs/current", json={"name": "Renamed Co"})
    client.post("/api/members/invitations", json={"email": "someone@example.com", "role": "member"})

    res = client.get("/api/settings/audit-logs")
    assert res.status_code == 200
    body = res.json()
    entries = body["items"]
    actions = [e["action"] for e in entries]
    assert "org.created" in actions
    assert "org.renamed" in actions
    assert "member.invited" in actions
    assert all(e["actor_email"] == "user@example.com" for e in entries)


def test_audit_log_empty_for_fresh_org_action_free(client):
    from .conftest import otp_login, create_org

    otp_login(client, "quiet@example.com")
    create_org(client, "Quiet Co")
    body = client.get("/api/settings/audit-logs").json()
    # org.created itself is logged, so there's always at least one entry.
    assert body["total"] == 1
    assert body["items"][0]["action"] == "org.created"


def test_audit_log_requires_admin(auth_client):
    client, org = auth_client
    # Downgrade the caller to a plain member of their own org to confirm
    # the endpoint is now admin-gated (it used to be open to any member).
    from app import models
    from app.db import SessionLocal

    db = SessionLocal()
    try:
        membership = db.query(models.Membership).filter_by(org_id=org["id"]).first()
        membership.role = "member"
        db.commit()
    finally:
        db.close()

    res = client.get("/api/settings/audit-logs")
    assert res.status_code == 403


def test_request_log_records_mutating_and_error_requests(auth_client):
    client, org = auth_client

    client.patch("/api/orgs/current", json={"name": "Renamed Again"})
    client.get("/api/pentests/does-not-exist")  # 404, should be logged despite being a GET

    res = client.get("/api/settings/request-logs")
    assert res.status_code == 200
    body = res.json()
    paths = [(e["method"], e["status_code"], e["path"]) for e in body["items"]]
    assert ("PATCH", 200, "/api/orgs/current") in paths
    assert ("GET", 404, "/api/pentests/does-not-exist") in paths
    # A plain, successful GET must never appear.
    assert not any(method == "GET" and status_code < 400 for method, status_code, _ in paths)


def test_audit_log_filters_by_actor_action_and_date_range(auth_client):
    client, org = auth_client
    client.patch("/api/orgs/current", json={"name": "Renamed Co"})

    me = client.get("/api/auth/me").json()
    actor_id = me["user"]["id"]

    by_actor = client.get(f"/api/settings/audit-logs?actor_user_id={actor_id}").json()
    assert by_actor["total"] >= 1

    by_action = client.get("/api/settings/audit-logs?action=renamed").json()
    assert all("renamed" in e["action"] for e in by_action["items"])

    from_future = client.get("/api/settings/audit-logs?date_from=2099-01-01").json()
    assert from_future["total"] == 0

    to_past = client.get("/api/settings/audit-logs?date_to=2000-01-01").json()
    assert to_past["total"] == 0

    # A malformed date string is treated as "no filter" rather than erroring.
    malformed = client.get("/api/settings/audit-logs?date_from=not-a-date")
    assert malformed.status_code == 200


def test_request_log_filters_by_method_status_and_date_range(auth_client):
    client, org = auth_client
    client.patch("/api/orgs/current", json={"name": "Renamed Again"})
    client.get("/api/pentests/does-not-exist")  # 404

    by_method = client.get("/api/settings/request-logs?method=patch").json()
    assert all(e["method"] == "PATCH" for e in by_method["items"])

    by_min_status = client.get("/api/settings/request-logs?min_status=404").json()
    assert all(e["status_code"] >= 404 for e in by_min_status["items"])

    from_future = client.get("/api/settings/request-logs?date_from=2099-01-01").json()
    assert from_future["total"] == 0

    to_past = client.get("/api/settings/request-logs?date_to=2000-01-01").json()
    assert to_past["total"] == 0


def test_request_log_requires_admin(auth_client):
    client, org = auth_client
    from app import models
    from app.db import SessionLocal

    db = SessionLocal()
    try:
        membership = db.query(models.Membership).filter_by(org_id=org["id"]).first()
        membership.role = "member"
        db.commit()
    finally:
        db.close()

    res = client.get("/api/settings/request-logs")
    assert res.status_code == 403
