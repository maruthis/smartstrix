def test_mutating_session_request_requires_csrf_header(auth_client):
    client, _org = auth_client
    csrf = client.headers.pop("x-csrf-token")

    missing = client.post("/api/orgs", json={"name": "No CSRF"})
    assert missing.status_code == 403
    assert missing.json()["detail"] == "csrf_failed"

    bad = client.post("/api/orgs", headers={"x-csrf-token": "wrong"}, json={"name": "Bad CSRF"})
    assert bad.status_code == 403

    good = client.post("/api/orgs", headers={"x-csrf-token": csrf}, json={"name": "Good CSRF"})
    assert good.status_code == 200
