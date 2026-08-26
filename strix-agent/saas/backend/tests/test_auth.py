from .conftest import create_org, otp_login


def test_otp_start_returns_dev_code_in_dev_mode(client):
    res = client.post("/api/auth/otp/start", json={"email": "a@example.com"})
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert len(body["dev_code"]) == 6


def test_otp_verify_wrong_code_rejected(client):
    client.post("/api/auth/otp/start", json={"email": "a@example.com"})
    res = client.post("/api/auth/otp/verify", json={"email": "a@example.com", "code": "000000"})
    assert res.status_code == 403
    assert res.json()["detail"] == "invalid_or_expired_code"


def test_otp_verify_creates_user_and_session(client):
    otp_login(client, "new-user@example.com")
    me = client.get("/api/auth/me")
    assert me.status_code == 200
    body = me.json()
    assert body["user"]["email"] == "new-user@example.com"
    assert body["active_org"] is None
    assert body["organizations"] == []


def test_me_requires_session(client):
    res = client.get("/api/auth/me")
    assert res.status_code == 401
    assert res.json()["detail"] == "not_authenticated"


def test_login_sets_a_server_side_session_expiry(client):
    from datetime import timedelta

    from app import models
    from app.db import SessionLocal
    from app.time_utils import utcnow

    otp_login(client, "expiry-check@example.com")

    db = SessionLocal()
    try:
        sess = db.query(models.Session_).filter_by(user_id=db.query(models.User).filter_by(email="expiry-check@example.com").first().id).first()
        assert sess.expires_at is not None
        # ~30 days out (auth.py's SESSION_TTL) — a loose bound so this
        # doesn't break if that constant's exact value ever changes.
        assert timedelta(days=25) < (sess.expires_at - utcnow()) < timedelta(days=35)
    finally:
        db.close()


def test_expired_session_is_rejected_and_deleted(client):
    from datetime import timedelta

    from app import models
    from app.db import SessionLocal
    from app.time_utils import utcnow

    otp_login(client, "expired@example.com")
    token = client.cookies.get("strix_saas_session")

    db = SessionLocal()
    try:
        sess = db.get(models.Session_, token)
        sess.expires_at = utcnow() - timedelta(days=1)
        db.commit()
    finally:
        db.close()

    res = client.get("/api/auth/me")
    assert res.status_code == 401
    assert res.json()["detail"] == "session_expired"

    db = SessionLocal()
    try:
        assert db.get(models.Session_, token) is None
    finally:
        db.close()


def test_session_predating_the_expiry_column_still_works(client):
    """A session row with expires_at=None (created before this column
    existed) is a one-time adoption allowance, not an ongoing bypass — see
    deps.py's current_session()."""
    from app import models
    from app.db import SessionLocal

    otp_login(client, "legacy-session@example.com")
    token = client.cookies.get("strix_saas_session")

    db = SessionLocal()
    try:
        sess = db.get(models.Session_, token)
        sess.expires_at = None
        db.commit()
    finally:
        db.close()

    res = client.get("/api/auth/me")
    assert res.status_code == 200


def test_otp_verify_second_login_reuses_active_org(client):
    otp_login(client, "repeat@example.com")
    org = create_org(client, "Repeat Co")

    client.post("/api/auth/logout")
    otp_login(client, "repeat@example.com")
    me = client.get("/api/auth/me").json()
    assert me["active_org"]["id"] == org["id"]
    assert me["role"] == "admin"


def test_switch_org_rejects_non_member(client):
    otp_login(client)
    res = client.post("/api/auth/switch-org", json={"org_id": "does-not-exist"})
    assert res.status_code == 403
    assert res.json()["detail"] == "not_a_member"


def test_logout_clears_session(client):
    otp_login(client)
    assert client.get("/api/auth/me").status_code == 200
    res = client.post("/api/auth/logout")
    assert res.status_code == 200
    assert client.get("/api/auth/me").status_code == 401


def test_org_scoped_endpoint_requires_active_org(client):
    otp_login(client)
    res = client.get("/api/repositories")
    assert res.status_code == 400
    assert res.json()["detail"] == "no_active_org"


def test_otp_verify_locks_out_after_max_attempts(client):
    start = client.post("/api/auth/otp/start", json={"email": "brute@example.com"})
    real_code = start.json()["dev_code"]

    for _ in range(5):
        res = client.post("/api/auth/otp/verify", json={"email": "brute@example.com", "code": "000000"})
        assert res.status_code == 403
        assert res.json()["detail"] == "invalid_or_expired_code"

    # The 6th attempt is locked out even though attempts so far were all
    # wrong-guesses, not the real code.
    locked = client.post("/api/auth/otp/verify", json={"email": "brute@example.com", "code": "000000"})
    assert locked.status_code == 429
    assert locked.json()["detail"] == "too_many_attempts"

    # The real code no longer works either, once locked out: the OTP row is
    # consumed at lockout, so it no longer matches the "most recent
    # unconsumed code" lookup and falls into the generic expired/invalid
    # path rather than reporting too_many_attempts a second time.
    real_attempt = client.post("/api/auth/otp/verify", json={"email": "brute@example.com", "code": real_code})
    assert real_attempt.status_code == 403
    assert real_attempt.json()["detail"] == "invalid_or_expired_code"


def test_otp_start_rate_limited_per_email(client):
    for _ in range(5):
        res = client.post("/api/auth/otp/start", json={"email": "flood@example.com"})
        assert res.status_code == 200
    blocked = client.post("/api/auth/otp/start", json={"email": "flood@example.com"})
    assert blocked.status_code == 429
    assert blocked.json()["detail"] == "too_many_otp_requests"


def test_otp_verify_lockout_does_not_block_a_freshly_requested_code(client):
    client.post("/api/auth/otp/start", json={"email": "brute2@example.com"})
    for _ in range(5):
        client.post("/api/auth/otp/verify", json={"email": "brute2@example.com", "code": "000000"})

    # Requesting a brand-new code resets the attempt budget.
    new_start = client.post("/api/auth/otp/start", json={"email": "brute2@example.com"})
    new_code = new_start.json()["dev_code"]
    res = client.post("/api/auth/otp/verify", json={"email": "brute2@example.com", "code": new_code})
    assert res.status_code == 200
