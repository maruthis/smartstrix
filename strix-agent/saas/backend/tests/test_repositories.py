import time

from .conftest import add_member, add_repo


def test_list_repositories_empty(auth_client):
    client, _org = auth_client
    res = client.get("/api/repositories")
    assert res.status_code == 200
    assert res.json() == []


def test_installable_excludes_already_added(auth_client):
    client, _org = auth_client
    before = client.get("/api/repositories/installable").json()
    assert len(before) == 3

    add_repo(client, before[0]["full_name"])

    after = client.get("/api/repositories/installable").json()
    assert len(after) == 2
    assert before[0]["full_name"] not in [r["full_name"] for r in after]


def test_add_repository_conflict(auth_client):
    client, _org = auth_client
    add_repo(client, "acme/widgets")
    res = client.post("/api/repositories", json={"full_name": "acme/widgets"})
    assert res.status_code == 409
    assert res.json()["detail"] == "already_added"


def test_update_repository_toggle_auto_review(auth_client):
    client, _org = auth_client
    repo = add_repo(client)
    assert repo["auto_review_enabled"] is True

    res = client.patch(f"/api/repositories/{repo['id']}", json={"auto_review_enabled": False})
    assert res.status_code == 200
    assert res.json()["auto_review_enabled"] is False


def test_update_repository_not_found(auth_client):
    client, _org = auth_client
    res = client.patch("/api/repositories/does-not-exist", json={"auto_review_enabled": False})
    assert res.status_code == 404


def test_remove_repository(auth_client):
    client, _org = auth_client
    repo = add_repo(client)
    res = client.request("DELETE", f"/api/repositories/{repo['id']}")
    assert res.status_code == 200
    assert client.get("/api/repositories").json() == []


def test_remove_repository_not_found(auth_client):
    client, _org = auth_client
    res = client.request("DELETE", "/api/repositories/does-not-exist")
    assert res.status_code == 404


def test_trigger_scan_creates_pentest(auth_client):
    client, _org = auth_client
    repo = add_repo(client)
    res = client.post(f"/api/repositories/{repo['id']}/scan")
    assert res.status_code == 200
    pentest_id = res.json()["pentest_id"]
    assert client.get(f"/api/pentests/{pentest_id}").status_code == 200


def test_repository_open_issues_count_reflected(auth_client):
    client, _org = auth_client
    repo = add_repo(client)
    listing = client.get("/api/repositories").json()
    assert listing[0]["open_issues_count"] == 0


def test_repository_open_issues_count_across_multiple_repos(auth_client):
    """Regression check for the N+1 -> batched-aggregate refactor: each
    repo's count must stay correctly attributed to that repo, including
    one with zero issues and one whose only issue is fixed (excluded)."""
    client, _org = auth_client
    repo_a = add_repo(client, "acme/widgets")
    repo_b = add_repo(client, "acme/gadgets")
    repo_c = add_repo(client, "acme/empty")

    for repo in (repo_a, repo_b):
        pentest = client.post("/api/pentests", json={"target_type": "repository", "target_id": repo["id"]}).json()
        deadline = time.time() + 5
        while time.time() < deadline:
            if client.get(f"/api/pentests/{pentest['id']}").json()["status"] == "completed":
                break
            time.sleep(0.02)

    counts = {r["id"]: r["open_issues_count"] for r in client.get("/api/repositories").json()}
    assert counts[repo_a["id"]] > 0
    assert counts[repo_b["id"]] > 0
    assert counts[repo_c["id"]] == 0
    # Total across repos matches the total non-fixed/ignored issue count.
    all_open = sum(1 for i in client.get("/api/issues?status_filter=open").json()["items"])
    assert counts[repo_a["id"]] + counts[repo_b["id"]] == all_open


def test_update_and_remove_repository_require_admin(auth_client):
    client, org = auth_client
    repo = add_repo(client)
    add_member(client, org)

    update = client.patch(f"/api/repositories/{repo['id']}", json={"auto_review_enabled": False})
    assert update.status_code == 403
    assert update.json()["detail"] == "admin_required"

    remove = client.request("DELETE", f"/api/repositories/{repo['id']}")
    assert remove.status_code == 403

    # A member can still list and trigger scans.
    assert client.get("/api/repositories").status_code == 200
    assert client.post(f"/api/repositories/{repo['id']}/scan").status_code == 200


def test_installable_gitlab_is_empty_when_not_connected(auth_client):
    client, _org = auth_client
    res = client.get("/api/repositories/installable?provider=gitlab")
    assert res.status_code == 200
    assert res.json() == []


def test_installable_rejects_unsupported_provider(auth_client):
    client, _org = auth_client
    res = client.get("/api/repositories/installable?provider=bitbucket")
    assert res.status_code == 400
    assert res.json()["detail"] == "unsupported_provider"

    add = client.post("/api/repositories", json={"full_name": "acme/x", "provider": "bitbucket"})
    assert add.status_code == 400
    assert add.json()["detail"] == "unsupported_provider"


def test_installable_lists_real_repos_once_github_is_connected(auth_client, monkeypatch):
    from app.providers import git_hosting

    client, _org = auth_client
    monkeypatch.setattr(git_hosting, "verify_github", lambda *, token, base_url: "octocat")
    client.post("/api/integrations/github/connect", json={"account_label": "octocat", "credential": "ghp_real"})

    monkeypatch.setattr(
        git_hosting,
        "list_repos_github",
        lambda *, token, base_url: [{"full_name": "octocat/real-repo", "default_branch": "main", "private": False}],
    )
    res = client.get("/api/repositories/installable")
    assert res.status_code == 200
    assert res.json() == [{"full_name": "octocat/real-repo", "default_branch": "main", "private": False}]

    # Once added, it drops out of the installable list — scoped by provider,
    # so a same-named gitlab repo wouldn't be excluded by this add.
    client.post("/api/repositories", json={"full_name": "octocat/real-repo", "provider": "github"})
    assert client.get("/api/repositories/installable").json() == []


def test_installable_surfaces_revoked_credential_as_401(auth_client, monkeypatch):
    from app.providers import git_hosting

    client, _org = auth_client
    monkeypatch.setattr(git_hosting, "verify_github", lambda *, token, base_url: "octocat")
    client.post("/api/integrations/github/connect", json={"account_label": "octocat", "credential": "ghp_real"})

    def fake_list(*, token, base_url):
        raise git_hosting.CredentialError("invalid_credentials")

    monkeypatch.setattr(git_hosting, "list_repos_github", fake_list)
    res = client.get("/api/repositories/installable")
    assert res.status_code == 401
    assert res.json()["detail"] == "invalid_credentials"


def test_add_gitlab_repository(auth_client):
    client, _org = auth_client
    res = client.post("/api/repositories", json={"full_name": "acme-group/widgets", "provider": "gitlab"})
    assert res.status_code == 200
    assert res.json()["provider"] == "gitlab"

    # Same full_name under a different provider is not a conflict.
    other = client.post("/api/repositories", json={"full_name": "acme-group/widgets", "provider": "github"})
    assert other.status_code == 200


def test_list_repository_refs_returns_empty_without_a_connected_integration(auth_client):
    client, _org = auth_client
    add = client.post("/api/repositories", json={"full_name": "acme/x"})
    repo_id = add.json()["id"]

    res = client.get(f"/api/repositories/{repo_id}/refs")
    assert res.status_code == 200
    assert res.json() == []


def test_list_repository_refs_lists_branches_once_github_is_connected(auth_client, monkeypatch):
    from app.providers import git_hosting

    client, _org = auth_client
    monkeypatch.setattr(git_hosting, "verify_github", lambda *, token, base_url: "octocat")
    client.post("/api/integrations/github/connect", json={"account_label": "octocat", "credential": "ghp_real"})
    add = client.post("/api/repositories", json={"full_name": "octocat/widgets", "provider": "github"})
    repo_id = add.json()["id"]

    seen = {}

    def fake_list_branches(*, token, base_url, full_name):
        seen["full_name"] = full_name
        return [{"name": "main", "commit_sha": "aaa"}, {"name": "dev", "commit_sha": "bbb"}]

    monkeypatch.setattr(git_hosting, "list_branches_github", fake_list_branches)
    res = client.get(f"/api/repositories/{repo_id}/refs?ref_type=branches")
    assert res.status_code == 200
    assert res.json() == [{"name": "main", "commit_sha": "aaa"}, {"name": "dev", "commit_sha": "bbb"}]
    assert seen["full_name"] == "octocat/widgets"


def test_list_repository_refs_lists_tags_and_commits(auth_client, monkeypatch):
    from app.providers import git_hosting

    client, _org = auth_client
    monkeypatch.setattr(git_hosting, "verify_github", lambda *, token, base_url: "octocat")
    client.post("/api/integrations/github/connect", json={"account_label": "octocat", "credential": "ghp_real"})
    add = client.post("/api/repositories", json={"full_name": "octocat/widgets", "provider": "github"})
    repo_id = add.json()["id"]

    monkeypatch.setattr(
        git_hosting, "list_tags_github", lambda *, token, base_url, full_name: [{"name": "v1.0.0", "commit_sha": "ccc"}]
    )
    tags = client.get(f"/api/repositories/{repo_id}/refs?ref_type=tags")
    assert tags.status_code == 200
    assert tags.json() == [{"name": "v1.0.0", "commit_sha": "ccc"}]

    monkeypatch.setattr(
        git_hosting,
        "list_commits_github",
        lambda *, token, base_url, full_name: [{"sha": "ddd", "message": "Fix bug", "author_date": "2026-01-01T00:00:00Z"}],
    )
    commits = client.get(f"/api/repositories/{repo_id}/refs?ref_type=commits")
    assert commits.status_code == 200
    assert commits.json() == [{"sha": "ddd", "message": "Fix bug", "author_date": "2026-01-01T00:00:00Z"}]


def test_list_repository_refs_rejects_an_invalid_ref_type(auth_client):
    client, _org = auth_client
    add = client.post("/api/repositories", json={"full_name": "acme/x"})
    repo_id = add.json()["id"]

    res = client.get(f"/api/repositories/{repo_id}/refs?ref_type=commit-history")
    assert res.status_code == 400
    assert res.json()["detail"] == "invalid_ref_type"


def test_list_repository_refs_not_found_for_unknown_repo(auth_client):
    client, _org = auth_client
    res = client.get("/api/repositories/does-not-exist/refs")
    assert res.status_code == 404


def test_list_repository_refs_surfaces_revoked_credential_as_401(auth_client, monkeypatch):
    from app.providers import git_hosting

    client, _org = auth_client
    monkeypatch.setattr(git_hosting, "verify_github", lambda *, token, base_url: "octocat")
    client.post("/api/integrations/github/connect", json={"account_label": "octocat", "credential": "ghp_real"})
    add = client.post("/api/repositories", json={"full_name": "octocat/widgets", "provider": "github"})
    repo_id = add.json()["id"]

    def fake_list(*, token, base_url, full_name):
        raise git_hosting.CredentialError("invalid_credentials")

    monkeypatch.setattr(git_hosting, "list_branches_github", fake_list)
    res = client.get(f"/api/repositories/{repo_id}/refs")
    assert res.status_code == 401
    assert res.json()["detail"] == "invalid_credentials"


def test_list_repository_pull_requests_returns_empty_without_a_connected_integration(auth_client):
    client, _org = auth_client
    add = client.post("/api/repositories", json={"full_name": "acme/x"})
    repo_id = add.json()["id"]

    res = client.get(f"/api/repositories/{repo_id}/pull-requests")
    assert res.status_code == 200
    assert res.json() == []


def test_list_repository_pull_requests_lists_open_prs_once_github_is_connected(auth_client, monkeypatch):
    from app.providers import git_hosting

    client, _org = auth_client
    monkeypatch.setattr(git_hosting, "verify_github", lambda *, token, base_url: "octocat")
    client.post("/api/integrations/github/connect", json={"account_label": "octocat", "credential": "ghp_real"})
    add = client.post("/api/repositories", json={"full_name": "octocat/widgets", "provider": "github"})
    repo_id = add.json()["id"]

    seen = {}

    def fake_list_prs(*, token, base_url, full_name):
        seen["full_name"] = full_name
        return [
            {
                "number": 42,
                "title": "Add wallet withdraw endpoint",
                "author": "octocat",
                "source_branch": "feature/withdraw",
                "target_branch": "main",
                "url": "https://github.com/octocat/widgets/pull/42",
            }
        ]

    monkeypatch.setattr(git_hosting, "list_pull_requests_github", fake_list_prs)
    res = client.get(f"/api/repositories/{repo_id}/pull-requests")
    assert res.status_code == 200
    assert res.json() == [
        {
            "number": 42,
            "title": "Add wallet withdraw endpoint",
            "author": "octocat",
            "source_branch": "feature/withdraw",
            "target_branch": "main",
            "url": "https://github.com/octocat/widgets/pull/42",
        }
    ]
    assert seen["full_name"] == "octocat/widgets"


def test_list_repository_pull_requests_lists_open_mrs_once_gitlab_is_connected(auth_client, monkeypatch):
    from app.providers import git_hosting

    client, _org = auth_client
    monkeypatch.setattr(git_hosting, "verify_gitlab", lambda *, token, base_url: "laplacian")
    client.post("/api/integrations/gitlab/connect", json={"account_label": "laplacian", "credential": "glpat_real"})
    add = client.post("/api/repositories", json={"full_name": "acme-group/widgets", "provider": "gitlab"})
    repo_id = add.json()["id"]

    monkeypatch.setattr(
        git_hosting,
        "list_pull_requests_gitlab",
        lambda *, token, base_url, full_name: [
            {
                "number": 7,
                "title": "Fix CORS misconfiguration",
                "author": "laplacian",
                "source_branch": "fix/cors",
                "target_branch": "main",
                "url": "https://gitlab.com/acme-group/widgets/-/merge_requests/7",
            }
        ],
    )
    res = client.get(f"/api/repositories/{repo_id}/pull-requests")
    assert res.status_code == 200
    assert res.json()[0]["number"] == 7
    assert res.json()[0]["title"] == "Fix CORS misconfiguration"


def test_list_repository_pull_requests_not_found_for_unknown_repo(auth_client):
    client, _org = auth_client
    res = client.get("/api/repositories/does-not-exist/pull-requests")
    assert res.status_code == 404


def test_list_repository_pull_requests_surfaces_revoked_credential_as_401(auth_client, monkeypatch):
    from app.providers import git_hosting

    client, _org = auth_client
    monkeypatch.setattr(git_hosting, "verify_github", lambda *, token, base_url: "octocat")
    client.post("/api/integrations/github/connect", json={"account_label": "octocat", "credential": "ghp_real"})
    add = client.post("/api/repositories", json={"full_name": "octocat/widgets", "provider": "github"})
    repo_id = add.json()["id"]

    def fake_list(*, token, base_url, full_name):
        raise git_hosting.CredentialError("invalid_credentials")

    monkeypatch.setattr(git_hosting, "list_pull_requests_github", fake_list)
    res = client.get(f"/api/repositories/{repo_id}/pull-requests")
    assert res.status_code == 401
    assert res.json()["detail"] == "invalid_credentials"
