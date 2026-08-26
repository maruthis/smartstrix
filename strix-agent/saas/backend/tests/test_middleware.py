def test_request_logging_failure_does_not_break_the_request(auth_client, monkeypatch):
    # RequestLogMiddleware._record must swallow any error writing the log
    # row — logging is best-effort and must never surface to the caller.
    client, _org = auth_client
    from app import middleware

    def boom():
        raise RuntimeError("db unavailable")

    monkeypatch.setattr(middleware, "SessionLocal", boom)

    res = client.patch("/api/orgs/current", json={"name": "Still Works"})
    assert res.status_code == 200
    assert res.json()["name"] == "Still Works"
