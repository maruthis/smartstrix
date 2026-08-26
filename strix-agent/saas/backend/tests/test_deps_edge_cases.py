from app import models
from app.db import SessionLocal
from app.settings import settings


def test_current_session_rejects_unknown_token(client):
    client.cookies.set(settings.session_cookie_name, "not-a-real-session-token")
    res = client.get("/api/auth/me")
    assert res.status_code == 401
    assert res.json()["detail"] == "not_authenticated"


def test_current_user_rejects_session_whose_user_was_deleted(auth_client):
    client, _org = auth_client
    token = client.cookies.get(settings.session_cookie_name)
    assert token

    db = SessionLocal()
    try:
        session_row = db.get(models.Session_, token)
        db.delete(db.get(models.User, session_row.user_id))
        db.commit()
    finally:
        db.close()

    res = client.get("/api/auth/me")
    assert res.status_code == 401
    assert res.json()["detail"] == "not_authenticated"


def test_current_membership_rejects_orphaned_active_org(auth_client):
    """Session points at an org the user is no longer a member of (e.g. they
    were removed from the org by an admin in another session)."""
    client, org = auth_client
    token = client.cookies.get(settings.session_cookie_name)

    db = SessionLocal()
    try:
        session_row = db.get(models.Session_, token)
        membership = (
            db.query(models.Membership).filter_by(org_id=org["id"], user_id=session_row.user_id).first()
        )
        db.delete(membership)
        db.commit()
    finally:
        db.close()

    res = client.get("/api/repositories")
    assert res.status_code == 403
    assert res.json()["detail"] == "not_a_member"


def test_current_org_rejects_membership_pointing_at_deleted_org(auth_client):
    """A Membership row survives referencing an org_id that no longer has an
    Organization row (shouldn't normally happen given cascade deletes, but
    current_org defends against it directly rather than trusting the FK)."""
    client, org = auth_client
    token = client.cookies.get(settings.session_cookie_name)

    db = SessionLocal()
    try:
        session_row = db.get(models.Session_, token)
        membership = (
            db.query(models.Membership).filter_by(org_id=org["id"], user_id=session_row.user_id).first()
        )
        membership.org_id = "orphaned-org-id"
        session_row.active_org_id = "orphaned-org-id"
        db.commit()
    finally:
        db.close()

    res = client.get("/api/repositories")
    assert res.status_code == 404
    assert res.json()["detail"] == "org_not_found"
