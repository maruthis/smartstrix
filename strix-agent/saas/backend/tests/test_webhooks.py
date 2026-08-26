import json

from app import models, webhook_delivery
from app.db import SessionLocal


def test_create_list_delete_webhook(auth_client):
    client, _org = auth_client

    res = client.post("/api/settings/webhooks", json={"url": "https://example.com/hook"})
    assert res.status_code == 200
    webhook = res.json()
    assert webhook["events"] == ["pentest.completed", "issue.created", "pr_review.completed"]
    assert webhook["secret"]  # shown once, at creation

    listing = client.get("/api/settings/webhooks").json()
    assert len(listing) == 1
    assert "secret" not in listing[0]  # never re-exposed after creation

    delete = client.request("DELETE", f"/api/settings/webhooks/{webhook['id']}")
    assert delete.status_code == 200
    assert client.get("/api/settings/webhooks").json() == []


def test_delete_webhook_not_found(auth_client):
    client, _org = auth_client
    res = client.request("DELETE", "/api/settings/webhooks/does-not-exist")
    assert res.status_code == 404


def test_create_and_delete_webhook_require_admin(auth_client):
    from .conftest import add_member

    client, org = auth_client
    admin_webhook = client.post("/api/settings/webhooks", json={"url": "https://example.com/hook"}).json()

    add_member(client, org)
    create = client.post("/api/settings/webhooks", json={"url": "https://attacker.example.com/exfil"})
    assert create.status_code == 403
    assert create.json()["detail"] == "admin_required"

    delete = client.request("DELETE", f"/api/settings/webhooks/{admin_webhook['id']}")
    assert delete.status_code == 403

    # A member can still see the (secret-free) list.
    listing = client.get("/api/settings/webhooks").json()
    assert len(listing) == 1
    assert "secret" not in listing[0]


def test_deliver_event_signs_payload_and_marks_status(auth_client, monkeypatch):
    _client, org = auth_client
    db = SessionLocal()
    try:
        webhook = models.Webhook(org_id=org["id"], url="https://example.com/hook", events=["pentest.completed"], secret="secret")
        db.add(webhook)
        db.commit()
        webhook_id = webhook.id
    finally:
        db.close()

    calls = []

    class _Response:
        status_code = 204

    class _Client:
        def __init__(self, timeout):
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def post(self, url, content, headers):
            calls.append({"url": url, "content": content, "headers": headers})
            return _Response()

    monkeypatch.setattr(webhook_delivery.httpx, "Client", _Client)
    monkeypatch.setattr(webhook_delivery, "hostname_resolves_public", lambda _host: True)

    webhook_delivery.deliver_event(org["id"], "pentest.completed", {"pentest_id": "p1"})

    assert len(calls) == 1
    assert calls[0]["headers"]["x-strix-event"] == "pentest.completed"
    assert calls[0]["headers"]["x-strix-signature"].startswith("sha256=")
    assert json.loads(calls[0]["content"]) == {"event": "pentest.completed", "payload": {"pentest_id": "p1"}}

    db = SessionLocal()
    try:
        assert db.get(models.Webhook, webhook_id).status == "active"
    finally:
        db.close()


def test_create_webhook_rejects_internal_urls(auth_client):
    client, _org = auth_client
    res = client.post("/api/settings/webhooks", json={"url": "http://example.com/hook"})
    assert res.status_code == 400
    assert res.json()["detail"] == "invalid_webhook_url"

    res = client.post("/api/settings/webhooks", json={"url": "https://127.0.0.1/hook"})
    assert res.status_code == 400
    assert res.json()["detail"] == "invalid_webhook_url"

    res = client.post("/api/settings/webhooks", json={"url": "https://169.254.169.254/latest/meta-data"})
    assert res.status_code == 400


def test_deliver_event_skips_non_public_hosts(auth_client, monkeypatch):
    _client, org = auth_client
    db = SessionLocal()
    try:
        webhook = models.Webhook(org_id=org["id"], url="https://example.com/hook", events=["pentest.completed"], secret="secret")
        db.add(webhook)
        db.commit()
        webhook_id = webhook.id
    finally:
        db.close()

    calls = []

    class _Client:
        def __init__(self, timeout):
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def post(self, url, content, headers):
            calls.append(url)
            raise AssertionError("must not POST to a non-public host")

    monkeypatch.setattr(webhook_delivery.httpx, "Client", _Client)
    monkeypatch.setattr(webhook_delivery, "hostname_resolves_public", lambda _host: False)

    webhook_delivery.deliver_event(org["id"], "pentest.completed", {"pentest_id": "p1"})
    assert calls == []

    db = SessionLocal()
    try:
        assert db.get(models.Webhook, webhook_id).status == "failing"
    finally:
        db.close()
