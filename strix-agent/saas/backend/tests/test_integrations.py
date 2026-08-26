from app.db import SessionLocal
from app.providers import git_hosting
from app.routers.integrations import list_live_pull_requests, list_live_refs, list_live_repos

from .conftest import add_member


def _mock_verify_ok(monkeypatch, provider: str, username: str = "octocat"):
    monkeypatch.setattr(git_hosting, f"verify_{provider}", lambda *, token, base_url: username)


def test_list_integrations_starts_all_disconnected(auth_client):
    client, _org = auth_client
    res = client.get("/api/integrations")
    assert res.status_code == 200
    body = res.json()
    assert len(body) == 7
    assert all(i["status"] == "not_connected" for i in body)
    assert all(i["account_label"] is None for i in body)
    github = next(i for i in body if i["provider"] == "github")
    assert github["category"] == "code"
    assert github["coming_soon"] is False
    assert github["live"] is True
    # No configure_url: it's a per-org access token, not a GitHub-App-style
    # installation, so there's no provider-side settings page to link to.
    assert github["configure_url"] is None
    gitlab = next(i for i in body if i["provider"] == "gitlab")
    assert gitlab["live"] is True
    assert gitlab["configure_url"] is None
    bitbucket = next(i for i in body if i["provider"] == "bitbucket")
    assert bitbucket["configure_url"] is None
    assert bitbucket["live"] is False
    msteams = next(i for i in body if i["provider"] == "msteams")
    assert msteams["coming_soon"] is True


def test_connect_github_verifies_live_before_saving(auth_client, monkeypatch):
    client, _org = auth_client
    calls = {}

    def fake_verify(*, token, base_url):
        calls["token"] = token
        calls["base_url"] = base_url
        return "octocat"

    monkeypatch.setattr(git_hosting, "verify_github", fake_verify)

    connect = client.post(
        "/api/integrations/github/connect",
        json={"account_label": "maruthis", "credential": "ghp_abcd1234", "base_url": "https://github.example.com"},
    )
    assert connect.status_code == 200
    body = connect.json()
    assert body["status"] == "connected"
    assert body["account_label"] == "maruthis"
    assert body["base_url"] == "https://github.example.com"
    assert body["credential_last4"] == "1234"
    assert body["connected_at"]
    assert calls == {"token": "ghp_abcd1234", "base_url": "https://github.example.com"}

    listing = client.get("/api/integrations").json()
    github = next(i for i in listing if i["provider"] == "github")
    assert github["status"] == "connected"
    assert github["credential_last4"] == "1234"

    disconnect = client.request("DELETE", "/api/integrations/github")
    assert disconnect.status_code == 200
    assert disconnect.json()["status"] == "not_connected"

    listing_after = client.get("/api/integrations").json()
    github_after = next(i for i in listing_after if i["provider"] == "github")
    assert github_after["status"] == "not_connected"
    assert github_after["credential_last4"] is None


def test_connect_gitlab_with_self_hosted_base_url(auth_client, monkeypatch):
    client, _org = auth_client
    _mock_verify_ok(monkeypatch, "gitlab", "acme-user")

    connect = client.post(
        "/api/integrations/gitlab/connect",
        json={"account_label": "acme-group", "credential": "glpat-secret", "base_url": "https://gitlab.acme.internal"},
    )
    assert connect.status_code == 200
    assert connect.json()["base_url"] == "https://gitlab.acme.internal"


def test_connect_github_without_credential_is_rejected(auth_client):
    client, _org = auth_client
    res = client.post("/api/integrations/github/connect", json={"account_label": "maruthis"})
    assert res.status_code == 400
    assert res.json()["detail"] == "credential_required"


def test_connect_github_rejects_invalid_credential(auth_client, monkeypatch):
    client, _org = auth_client

    def fake_verify(*, token, base_url):
        raise git_hosting.CredentialError("invalid_credentials")

    monkeypatch.setattr(git_hosting, "verify_github", fake_verify)
    res = client.post("/api/integrations/github/connect", json={"account_label": "maruthis", "credential": "bad-token"})
    assert res.status_code == 401
    assert res.json()["detail"] == "invalid_credentials"

    # Nothing was saved.
    listing = client.get("/api/integrations").json()
    assert next(i for i in listing if i["provider"] == "github")["status"] == "not_connected"


def test_connect_gitlab_surfaces_unreachable_provider_as_502(auth_client, monkeypatch):
    client, _org = auth_client

    def fake_verify(*, token, base_url):
        raise git_hosting.CredentialError("provider_unreachable")

    monkeypatch.setattr(git_hosting, "verify_gitlab", fake_verify)
    res = client.post("/api/integrations/gitlab/connect", json={"account_label": "x", "credential": "y", "base_url": "https://unreachable.example.com"})
    assert res.status_code == 502
    assert res.json()["detail"] == "provider_unreachable"


def test_connect_requires_a_non_blank_account_label(auth_client, monkeypatch):
    client, _org = auth_client
    _mock_verify_ok(monkeypatch, "github")
    res = client.post("/api/integrations/github/connect", json={"account_label": "   ", "credential": "x"})
    assert res.status_code == 400
    assert res.json()["detail"] == "account_label_required"


def test_connect_unknown_provider_404(auth_client):
    client, _org = auth_client
    res = client.post("/api/integrations/does-not-exist/connect", json={"account_label": "x"})
    assert res.status_code == 404


def test_disconnect_unknown_provider_404(auth_client):
    client, _org = auth_client
    res = client.request("DELETE", "/api/integrations/does-not-exist")
    assert res.status_code == 404


def test_connect_coming_soon_provider_rejected(auth_client):
    client, _org = auth_client
    res = client.post("/api/integrations/msteams/connect", json={"account_label": "x"})
    assert res.status_code == 400
    assert res.json()["detail"] == "provider_not_yet_available"


def test_connect_non_live_provider_does_not_require_credential(auth_client):
    client, _org = auth_client
    res = client.post("/api/integrations/jira/connect", json={"account_label": "acme-jira"})
    assert res.status_code == 200
    assert res.json()["credential_last4"] is None


def test_disconnect_never_connected_provider_is_a_noop(auth_client):
    client, _org = auth_client
    res = client.request("DELETE", "/api/integrations/slack")
    assert res.status_code == 200
    assert res.json()["status"] == "not_connected"


def test_reconnecting_updates_existing_row_instead_of_duplicating(auth_client, monkeypatch):
    client, _org = auth_client
    _mock_verify_ok(monkeypatch, "github")
    first = client.post("/api/integrations/github/connect", json={"account_label": "acme-one", "credential": "tok1"}).json()
    second = client.post("/api/integrations/github/connect", json={"account_label": "acme-two", "credential": "tok2"}).json()
    assert second["account_label"] == "acme-two"
    assert first["account_label"] != second["account_label"]

    listing = client.get("/api/integrations").json()
    assert sum(1 for i in listing if i["provider"] == "github") == 1


def test_list_live_repos_returns_none_for_a_non_live_provider(auth_client):
    _client, org = auth_client
    db = SessionLocal()
    try:
        assert list_live_repos(db, org["id"], "bitbucket") is None
    finally:
        db.close()


def test_list_live_refs_returns_empty_for_a_non_live_provider(auth_client):
    from app import models

    _client, org = auth_client
    db = SessionLocal()
    try:
        repo = models.Repository(org_id=org["id"], full_name="acme/x", provider="bitbucket")
        db.add(repo)
        db.commit()
        db.refresh(repo)
        assert list_live_refs(db, org["id"], repo, "branches") == []
    finally:
        db.close()


def test_list_live_refs_returns_empty_for_an_invalid_ref_type(auth_client):
    from app import models

    _client, org = auth_client
    db = SessionLocal()
    try:
        repo = models.Repository(org_id=org["id"], full_name="acme/x", provider="github")
        db.add(repo)
        db.commit()
        db.refresh(repo)
        assert list_live_refs(db, org["id"], repo, "not-a-real-type") == []
    finally:
        db.close()


def test_list_live_pull_requests_returns_empty_for_a_non_live_provider(auth_client):
    from app import models

    _client, org = auth_client
    db = SessionLocal()
    try:
        repo = models.Repository(org_id=org["id"], full_name="acme/x", provider="bitbucket")
        db.add(repo)
        db.commit()
        db.refresh(repo)
        assert list_live_pull_requests(db, org["id"], repo) == []
    finally:
        db.close()


def test_list_live_pull_requests_returns_empty_without_a_stored_credential(auth_client):
    from app import models

    _client, org = auth_client
    db = SessionLocal()
    try:
        repo = models.Repository(org_id=org["id"], full_name="acme/x", provider="github")
        db.add(repo)
        db.commit()
        db.refresh(repo)
        assert list_live_pull_requests(db, org["id"], repo) == []
    finally:
        db.close()


def test_connect_and_disconnect_require_admin(auth_client, monkeypatch):
    client, org = auth_client
    _mock_verify_ok(monkeypatch, "github")
    add_member(client, org)

    connect = client.post("/api/integrations/github/connect", json={"account_label": "maruthis", "credential": "x"})
    assert connect.status_code == 403
    assert connect.json()["detail"] == "admin_required"

    # A member can still see the (all-disconnected) list.
    listing = client.get("/api/integrations").json()
    assert all(i["status"] == "not_connected" for i in listing)

    disconnect = client.request("DELETE", "/api/integrations/github")
    assert disconnect.status_code == 403
