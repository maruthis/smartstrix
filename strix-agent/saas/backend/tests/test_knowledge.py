from .conftest import add_domain, add_repo


def test_add_and_list_knowledge(auth_client):
    client, _org = auth_client
    res = client.post("/api/knowledge", json={"type": "business_logic", "description": "Users can withdraw once per 24h."})
    assert res.status_code == 200
    entry = res.json()
    assert entry["scope_type"] == "global"

    listing = client.get("/api/knowledge").json()
    assert len(listing) == 1


def test_add_knowledge_requires_description(auth_client):
    client, _org = auth_client
    res = client.post("/api/knowledge", json={"description": "   "})
    assert res.status_code == 400
    assert res.json()["detail"] == "description_required"


def test_knowledge_search_filter(auth_client):
    client, _org = auth_client
    client.post("/api/knowledge", json={"description": "Payments are processed via Stripe."})
    client.post("/api/knowledge", json={"description": "Auth uses JWT with 1h expiry."})

    res = client.get("/api/knowledge?search=Stripe").json()
    assert len(res) == 1
    assert "Stripe" in res[0]["description"]


def test_knowledge_scope_filter(auth_client):
    client, _org = auth_client
    repo = add_repo(client)
    client.post("/api/knowledge", json={"description": "Global note"})
    client.post("/api/knowledge", json={"description": "Repo-scoped note", "scope_type": "repository", "scope_id": repo["id"]})

    only_repo_scoped = client.get("/api/knowledge?scope_type=repository").json()
    assert len(only_repo_scoped) == 1
    assert only_repo_scoped[0]["scope_id"] == repo["id"]

    all_scopes = client.get("/api/knowledge?scope_type=all").json()
    assert len(all_scopes) == 2


def test_add_knowledge_requires_scope_id_for_scoped_entries(auth_client):
    client, _org = auth_client
    res = client.post("/api/knowledge", json={"description": "Repo note", "scope_type": "repository", "scope_id": ""})
    assert res.status_code == 400
    assert res.json()["detail"] == "scope_id_required"


def test_delete_knowledge(auth_client):
    client, _org = auth_client
    entry = client.post("/api/knowledge", json={"description": "Temp note"}).json()
    res = client.request("DELETE", f"/api/knowledge/{entry['id']}")
    assert res.status_code == 200
    assert client.get("/api/knowledge").json() == []


def test_delete_knowledge_not_found(auth_client):
    client, _org = auth_client
    res = client.request("DELETE", "/api/knowledge/does-not-exist")
    assert res.status_code == 404


def test_relevant_entries_resolves_global_and_scoped(auth_client):
    from app import models
    from app.db import SessionLocal
    from app.routers.knowledge import relevant_entries

    client, org = auth_client
    repo = add_repo(client)
    domain = add_domain(client)

    client.post("/api/knowledge", json={"description": "Global"})
    client.post("/api/knowledge", json={"description": "Repo-scoped", "scope_type": "repository", "scope_id": repo["id"]})
    client.post("/api/knowledge", json={"description": "Domain-scoped", "scope_type": "domain", "scope_id": domain["id"]})
    client.post("/api/knowledge", json={"description": "Other repo-scoped", "scope_type": "repository", "scope_id": "some-other-repo"})

    db = SessionLocal()
    try:
        entries = relevant_entries(db, org["id"], repository_id=repo["id"], domain_id=None)
        descriptions = {e.description for e in entries}
        assert descriptions == {"Global", "Repo-scoped"}

        entries_none = relevant_entries(db, org["id"])
        assert {e.description for e in entries_none} == {"Global"}
    finally:
        db.close()
