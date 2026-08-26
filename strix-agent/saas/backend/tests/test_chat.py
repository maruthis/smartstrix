from app.routers import chat, pentests


def _enable_real_scan(monkeypatch):
    monkeypatch.setattr(chat.settings, "enable_real_scan", True)


def _stub_enqueue(monkeypatch):
    """Chat triggers a real pentest via create_and_enqueue_pentest, which
    calls jobs.enqueue_pentest — stub it so these tests never touch the
    real job queue/worker (live during tests via TestClient's lifespan),
    matching the same pattern used for PR review tests."""
    calls: list[str] = []

    async def _fake_enqueue(pentest_id: str) -> None:
        calls.append(pentest_id)

    monkeypatch.setattr(pentests, "enqueue_pentest", _fake_enqueue)
    return calls


def test_suggestions(auth_client):
    client, _org = auth_client
    res = client.get("/api/chat/suggestions")
    assert res.status_code == 200
    body = res.json()
    assert "web" in body["categories"]
    assert len(body["suggestions"]["web"]) == 4


def test_session_and_message_flow(auth_client):
    client, _org = auth_client

    session = client.post("/api/chat/sessions", json={"category": "web"}).json()
    assert session["title"] == "New chat"

    sessions = client.get("/api/chat/sessions").json()
    assert len(sessions) == 1

    messages = client.post(f"/api/chat/sessions/{session['id']}/messages", json={"content": "Test API authorization"})
    assert messages.status_code == 200
    body = messages.json()
    assert len(body) == 2
    assert body[0]["role"] == "user"
    assert body[1]["role"] == "assistant"

    updated_session = client.get("/api/chat/sessions").json()[0]
    assert updated_session["title"] == "Test API authorization"

    history = client.get(f"/api/chat/sessions/{session['id']}/messages").json()
    assert len(history) == 2


def test_send_message_without_a_repository_asks_to_attach_one(auth_client):
    """No fabricated "I'll start a review" — chat can't scan anything
    without a target, so it says so plainly."""
    client, _org = auth_client
    session = client.post("/api/chat/sessions", json={"category": "web"}).json()
    reply = client.post(f"/api/chat/sessions/{session['id']}/messages", json={"content": "Test API authorization"}).json()[1]
    assert "Add repositories" in reply["content"]
    assert "can't scan" in reply["content"]


def test_send_message_with_repository_but_real_scan_disabled(auth_client):
    from .conftest import add_repo

    client, _org = auth_client
    repo = add_repo(client)
    session = client.post("/api/chat/sessions", json={"category": "code"}).json()
    reply = client.post(
        f"/api/chat/sessions/{session['id']}/messages",
        json={"content": "Audit this repo", "repository_ids": [repo["id"]]},
    ).json()[1]
    assert "Real scanning isn't enabled" in reply["content"]


def test_send_message_triggers_a_real_pentest_per_repository(auth_client, monkeypatch):
    from .conftest import add_repo
    from app import models
    from app.db import SessionLocal

    _enable_real_scan(monkeypatch)
    calls = _stub_enqueue(monkeypatch)
    client, _org = auth_client
    repo_a = add_repo(client, "acme/widgets")
    repo_b = add_repo(client, "acme/gadgets")

    session = client.post("/api/chat/sessions", json={"category": "code"}).json()
    reply = client.post(
        f"/api/chat/sessions/{session['id']}/messages",
        json={"content": "Audit both repos for injection flaws", "repository_ids": [repo_a["id"], repo_b["id"]]},
    ).json()[1]

    assert "Started a real scan for" in reply["content"]
    assert "acme/widgets" in reply["content"]
    assert "acme/gadgets" in reply["content"]
    assert "background" in reply["content"]
    assert len(calls) == 2

    db = SessionLocal()
    try:
        pentests_created = db.query(models.Pentest).filter_by(target_type="repository").all()
        assert len(pentests_created) == 2
        assert {p.target_id for p in pentests_created} == {repo_a["id"], repo_b["id"]}
        assert all(p.custom_instructions == "Audit both repos for injection flaws" for p in pentests_created)
        assert all(p.scan_mode == "quick" for p in pentests_created)
    finally:
        db.close()


def test_send_message_with_knowledge_context(auth_client, monkeypatch):
    from .conftest import add_repo

    _enable_real_scan(monkeypatch)
    _stub_enqueue(monkeypatch)
    client, _org = auth_client
    repo = add_repo(client)
    client.post("/api/knowledge", json={"description": "Rate limit is 100 req/min.", "scope_type": "repository", "scope_id": repo["id"]})

    session = client.post("/api/chat/sessions", json={"category": "code"}).json()
    res = client.post(
        f"/api/chat/sessions/{session['id']}/messages",
        json={"content": "Audit the rate limiter", "repository_ids": [repo["id"]]},
    )
    reply = res.json()[1]["content"]
    assert "1 piece(s)" in reply


def test_send_message_ignores_repository_ids_from_another_org(auth_client, monkeypatch):
    """A repository_id that doesn't belong to this org must not be
    scannable just because the caller passed its id."""
    _enable_real_scan(monkeypatch)
    _stub_enqueue(monkeypatch)
    client, _org = auth_client

    from app import models
    from app.db import SessionLocal

    db = SessionLocal()
    try:
        other_org = models.Organization(name="OtherOrg")
        db.add(other_org)
        db.flush()
        other_repo = models.Repository(org_id=other_org.id, full_name="other/repo")
        db.add(other_repo)
        db.commit()
        other_repo_id = other_repo.id
    finally:
        db.close()

    session = client.post("/api/chat/sessions", json={"category": "code"}).json()
    reply = client.post(
        f"/api/chat/sessions/{session['id']}/messages",
        json={"content": "Audit this", "repository_ids": [other_repo_id]},
    ).json()[1]
    assert "couldn't find those repositories" in reply["content"]


def test_send_message_empty_content_rejected(auth_client):
    client, _org = auth_client
    session = client.post("/api/chat/sessions", json={}).json()
    res = client.post(f"/api/chat/sessions/{session['id']}/messages", json={"content": "   "})
    assert res.status_code == 400
    assert res.json()["detail"] == "content_required"


def test_session_not_found(auth_client):
    client, _org = auth_client
    res = client.get("/api/chat/sessions/does-not-exist/messages")
    assert res.status_code == 404

    res = client.post("/api/chat/sessions/does-not-exist/messages", json={"content": "hi"})
    assert res.status_code == 404


def test_chat_messages_are_owner_scoped_within_an_org(auth_client):
    """Another member of the same org must not read or write someone else's thread."""
    from .conftest import add_member

    client, org = auth_client
    session = client.post("/api/chat/sessions", json={"category": "web"}).json()
    client.post(f"/api/chat/sessions/{session['id']}/messages", json={"content": "secret prompt"})

    add_member(client, org)
    history = client.get(f"/api/chat/sessions/{session['id']}/messages")
    assert history.status_code == 404
    send = client.post(f"/api/chat/sessions/{session['id']}/messages", json={"content": "hijack"})
    assert send.status_code == 404
    assert client.get("/api/chat/sessions").json() == []
