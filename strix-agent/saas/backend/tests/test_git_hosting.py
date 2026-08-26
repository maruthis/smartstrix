"""Exercises the real HTTP request-building/response-parsing logic in
app/providers/git_hosting.py against an httpx.MockTransport instead of the
real network — this is what actually proves the GitHub/GitLab API calls
are built correctly (headers, URLs, self-hosted base_url handling, error
mapping), which router-level tests that monkeypatch these functions
outright can't cover."""

import httpx
import pytest

from app.providers import git_hosting


def _client_with(handler):
    def factory() -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(handler))

    return factory


def test_verify_github_returns_login_on_success(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://api.github.com/user"
        assert request.headers["authorization"] == "Bearer ghp_test"
        assert request.headers["accept"] == "application/vnd.github+json"
        return httpx.Response(200, json={"login": "octocat"})

    monkeypatch.setattr(git_hosting, "_client", _client_with(handler))
    assert git_hosting.verify_github(token="ghp_test", base_url=None) == "octocat"


def test_verify_github_uses_enterprise_api_v3_base_when_base_url_given(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://github.acme.internal/api/v3/user"
        return httpx.Response(200, json={"login": "acme-user"})

    monkeypatch.setattr(git_hosting, "_client", _client_with(handler))
    result = git_hosting.verify_github(token="t", base_url="https://github.acme.internal")
    assert result == "acme-user"


def test_verify_github_raises_on_401(monkeypatch):
    monkeypatch.setattr(git_hosting, "_client", _client_with(lambda r: httpx.Response(401, json={})))
    with pytest.raises(git_hosting.CredentialError) as exc_info:
        git_hosting.verify_github(token="bad", base_url=None)
    assert exc_info.value.code == "invalid_credentials"


def test_verify_github_raises_on_403(monkeypatch):
    monkeypatch.setattr(git_hosting, "_client", _client_with(lambda r: httpx.Response(403, json={})))
    with pytest.raises(git_hosting.CredentialError) as exc_info:
        git_hosting.verify_github(token="bad", base_url=None)
    assert exc_info.value.code == "invalid_credentials"


def test_verify_github_raises_provider_error_on_5xx(monkeypatch):
    monkeypatch.setattr(git_hosting, "_client", _client_with(lambda r: httpx.Response(500, json={})))
    with pytest.raises(git_hosting.CredentialError) as exc_info:
        git_hosting.verify_github(token="t", base_url=None)
    assert exc_info.value.code == "provider_error"


def test_verify_github_raises_provider_unreachable_on_network_error(monkeypatch):
    def factory() -> httpx.Client:
        def handler(request: httpx.Request):
            raise httpx.ConnectError("no route to host", request=request)

        return httpx.Client(transport=httpx.MockTransport(handler))

    monkeypatch.setattr(git_hosting, "_client", factory)
    with pytest.raises(git_hosting.CredentialError) as exc_info:
        git_hosting.verify_github(token="t", base_url=None)
    assert exc_info.value.code == "provider_unreachable"


def test_list_repos_github_maps_fields(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert "affiliation=owner" in str(request.url)
        return httpx.Response(
            200,
            json=[
                {"full_name": "octocat/pub", "default_branch": "main", "private": False},
                {"full_name": "octocat/priv", "default_branch": "trunk", "private": True},
                {"full_name": "octocat/no-default-branch"},
            ],
        )

    monkeypatch.setattr(git_hosting, "_client", _client_with(handler))
    repos = git_hosting.list_repos_github(token="t", base_url=None)
    assert repos == [
        {"full_name": "octocat/pub", "default_branch": "main", "private": False},
        {"full_name": "octocat/priv", "default_branch": "trunk", "private": True},
        {"full_name": "octocat/no-default-branch", "default_branch": "main", "private": False},
    ]


def test_list_repos_github_follows_link_header_pagination(monkeypatch):
    """A token with more than one page of accessible repos used to be
    silently truncated to whatever page 1 returned — the reported bug this
    covers: a real repo simply never showing up in the Add Repository
    picker because it lived on page 2+."""
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        calls.append(url)
        if "page=2" not in url:
            return httpx.Response(
                200,
                json=[{"full_name": "acme/page-one-repo", "default_branch": "main", "private": False}],
                headers={"Link": '<https://api.github.com/user/repos?per_page=100&page=2>; rel="next"'},
            )
        return httpx.Response(
            200,
            json=[{"full_name": "acme/page-two-repo", "default_branch": "main", "private": False}],
        )

    monkeypatch.setattr(git_hosting, "_client", _client_with(handler))
    repos = git_hosting.list_repos_github(token="t", base_url=None)
    assert [r["full_name"] for r in repos] == ["acme/page-one-repo", "acme/page-two-repo"]
    assert len(calls) == 2


def test_list_repos_github_stops_when_there_is_no_next_link(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[{"full_name": "acme/only-repo", "default_branch": "main", "private": False}])

    monkeypatch.setattr(git_hosting, "_client", _client_with(handler))
    repos = git_hosting.list_repos_github(token="t", base_url=None)
    assert len(repos) == 1


def test_verify_gitlab_uses_private_token_header_and_username_field(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://gitlab.com/api/v4/user"
        assert request.headers["private-token"] == "glpat-test"
        return httpx.Response(200, json={"username": "acme-user"})

    monkeypatch.setattr(git_hosting, "_client", _client_with(handler))
    assert git_hosting.verify_gitlab(token="glpat-test", base_url=None) == "acme-user"


def test_verify_gitlab_self_hosted_base_url(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://gitlab.acme.internal/api/v4/user"
        return httpx.Response(200, json={"username": "acme-user"})

    monkeypatch.setattr(git_hosting, "_client", _client_with(handler))
    git_hosting.verify_gitlab(token="t", base_url="https://gitlab.acme.internal/")


def test_list_repos_gitlab_maps_fields(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert "membership=true" in str(request.url)
        return httpx.Response(
            200,
            json=[
                {"path_with_namespace": "acme/widgets", "default_branch": "main", "visibility": "private"},
                {"path_with_namespace": "acme/public-thing", "default_branch": "main", "visibility": "public"},
                {"path_with_namespace": "acme/no-branch", "visibility": "internal"},
            ],
        )

    monkeypatch.setattr(git_hosting, "_client", _client_with(handler))
    repos = git_hosting.list_repos_gitlab(token="t", base_url=None)
    assert repos == [
        {"full_name": "acme/widgets", "default_branch": "main", "private": True},
        {"full_name": "acme/public-thing", "default_branch": "main", "private": False},
        {"full_name": "acme/no-branch", "default_branch": "main", "private": True},
    ]


def test_list_repos_gitlab_follows_x_next_page_pagination(monkeypatch):
    """Same bug as GitHub's, on GitLab's own pagination scheme: an
    enterprise GitLab instance with more than 100 accessible projects
    (e.g. via group/subgroup membership) was silently missing everything
    past page 1 — including a project like
    awgment-enterprise-modules/awgment-esb sitting on a later page."""
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        calls.append(url)
        if "page=2" in url:
            return httpx.Response(
                200,
                json=[
                    {
                        "path_with_namespace": "awgment-enterprise-modules/awgment-esb",
                        "default_branch": "main",
                        "visibility": "private",
                    }
                ],
                headers={"X-Next-Page": ""},
            )
        return httpx.Response(
            200,
            json=[{"path_with_namespace": "acme/widgets", "default_branch": "main", "visibility": "private"}],
            headers={"X-Next-Page": "2"},
        )

    monkeypatch.setattr(git_hosting, "_client", _client_with(handler))
    repos = git_hosting.list_repos_gitlab(token="t", base_url=None)
    assert [r["full_name"] for r in repos] == ["acme/widgets", "awgment-enterprise-modules/awgment-esb"]
    assert len(calls) == 2


def test_list_repos_gitlab_stops_when_x_next_page_is_absent(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json=[{"path_with_namespace": "acme/only-repo", "default_branch": "main", "visibility": "private"}]
        )

    monkeypatch.setattr(git_hosting, "_client", _client_with(handler))
    repos = git_hosting.list_repos_gitlab(token="t", base_url=None)
    assert len(repos) == 1


def test_list_repos_gitlab_pagination_is_capped_against_a_runaway_loop(monkeypatch):
    """A provider that (buggily, or via a malicious proxy) always claims
    there's a next page must not hang the request forever."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=[{"path_with_namespace": "acme/x", "default_branch": "main", "visibility": "private"}],
            headers={"X-Next-Page": "999"},  # always "more pages"
        )

    monkeypatch.setattr(git_hosting, "_client", _client_with(handler))
    repos = git_hosting.list_repos_gitlab(token="t", base_url=None)
    assert len(repos) == git_hosting._MAX_PAGES


def test_list_repos_gitlab_raises_invalid_credentials_on_401(monkeypatch):
    monkeypatch.setattr(git_hosting, "_client", _client_with(lambda r: httpx.Response(401, json={})))
    with pytest.raises(git_hosting.CredentialError) as exc_info:
        git_hosting.list_repos_gitlab(token="bad", base_url=None)
    assert exc_info.value.code == "invalid_credentials"


def test_list_branches_github_maps_fields(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://api.github.com/repos/octocat/widgets/branches?per_page=100"
        return httpx.Response(
            200,
            json=[
                {"name": "main", "commit": {"sha": "aaa111"}},
                {"name": "dev", "commit": {"sha": "bbb222"}},
            ],
        )

    monkeypatch.setattr(git_hosting, "_client", _client_with(handler))
    branches = git_hosting.list_branches_github(token="t", base_url=None, full_name="octocat/widgets")
    assert branches == [{"name": "main", "commit_sha": "aaa111"}, {"name": "dev", "commit_sha": "bbb222"}]


def test_list_tags_github_maps_fields(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://api.github.com/repos/octocat/widgets/tags?per_page=100"
        return httpx.Response(200, json=[{"name": "v1.0.0", "commit": {"sha": "ccc333"}}])

    monkeypatch.setattr(git_hosting, "_client", _client_with(handler))
    tags = git_hosting.list_tags_github(token="t", base_url=None, full_name="octocat/widgets")
    assert tags == [{"name": "v1.0.0", "commit_sha": "ccc333"}]


def test_list_commits_github_maps_fields_and_takes_first_message_line(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://api.github.com/repos/octocat/widgets/commits?per_page=50"
        return httpx.Response(
            200,
            json=[
                {
                    "sha": "ddd444",
                    "commit": {"message": "Fix the bug\n\nLonger body text here", "author": {"date": "2026-01-01T00:00:00Z"}},
                }
            ],
        )

    monkeypatch.setattr(git_hosting, "_client", _client_with(handler))
    commits = git_hosting.list_commits_github(token="t", base_url=None, full_name="octocat/widgets")
    assert commits == [{"sha": "ddd444", "message": "Fix the bug", "author_date": "2026-01-01T00:00:00Z"}]


def test_list_pull_requests_github_maps_fields(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://api.github.com/repos/octocat/widgets/pulls?state=open&per_page=100"
        return httpx.Response(
            200,
            json=[
                {
                    "number": 42,
                    "title": "Add wallet withdraw endpoint",
                    "user": {"login": "octocat"},
                    "head": {"ref": "feature/withdraw"},
                    "base": {"ref": "main"},
                    "html_url": "https://github.com/octocat/widgets/pull/42",
                }
            ],
        )

    monkeypatch.setattr(git_hosting, "_client", _client_with(handler))
    prs = git_hosting.list_pull_requests_github(token="t", base_url=None, full_name="octocat/widgets")
    assert prs == [
        {
            "number": 42,
            "title": "Add wallet withdraw endpoint",
            "author": "octocat",
            "source_branch": "feature/withdraw",
            "target_branch": "main",
            "url": "https://github.com/octocat/widgets/pull/42",
        }
    ]


def test_list_pull_requests_github_defaults_a_missing_author_to_unknown(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=[{"number": 1, "title": "No user field", "user": None, "head": {}, "base": {}, "html_url": None}],
        )

    monkeypatch.setattr(git_hosting, "_client", _client_with(handler))
    prs = git_hosting.list_pull_requests_github(token="t", base_url=None, full_name="octocat/widgets")
    assert prs[0]["author"] == "unknown"


def test_list_pull_requests_gitlab_maps_fields_using_the_project_scoped_iid(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://gitlab.com/api/v4/projects/acme%2Fwidgets/merge_requests?state=opened&scope=all&per_page=100&page=1"
        return httpx.Response(
            200,
            json=[
                {
                    "iid": 7,
                    "id": 999999,  # global id — must NOT be used as "number"
                    "title": "Fix CORS misconfiguration",
                    "author": {"username": "laplacian"},
                    "source_branch": "fix/cors",
                    "target_branch": "main",
                    "web_url": "https://gitlab.com/acme/widgets/-/merge_requests/7",
                }
            ],
        )

    monkeypatch.setattr(git_hosting, "_client", _client_with(handler))
    mrs = git_hosting.list_pull_requests_gitlab(token="t", base_url=None, full_name="acme/widgets")
    assert mrs == [
        {
            "number": 7,
            "title": "Fix CORS misconfiguration",
            "author": "laplacian",
            "source_branch": "fix/cors",
            "target_branch": "main",
            "url": "https://gitlab.com/acme/widgets/-/merge_requests/7",
        }
    ]


def test_list_pull_requests_gitlab_follows_pagination(monkeypatch):
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        if str(request.url).endswith("&page=1"):
            return httpx.Response(200, headers={"X-Next-Page": "2"}, json=[{"iid": 7, "title": "First MR", "author": {"username": "laplacian"}}])
        return httpx.Response(200, json=[{"iid": 8, "title": "Second MR", "author": {"username": "ada"}}])

    monkeypatch.setattr(git_hosting, "_client", _client_with(handler))
    mrs = git_hosting.list_pull_requests_gitlab(token="t", base_url=None, full_name="acme/widgets")
    assert [mr["number"] for mr in mrs] == [7, 8]
    assert seen == [
        "https://gitlab.com/api/v4/projects/acme%2Fwidgets/merge_requests?state=opened&scope=all&per_page=100&page=1",
        "https://gitlab.com/api/v4/projects/acme%2Fwidgets/merge_requests?state=opened&scope=all&per_page=100&page=2",
    ]


def test_list_pull_requests_github_raises_invalid_credentials_on_401(monkeypatch):
    monkeypatch.setattr(git_hosting, "_client", _client_with(lambda r: httpx.Response(401, json={})))
    with pytest.raises(git_hosting.CredentialError) as exc_info:
        git_hosting.list_pull_requests_github(token="bad", base_url=None, full_name="octocat/widgets")
    assert exc_info.value.code == "invalid_credentials"


def test_list_branches_gitlab_url_encodes_the_project_path(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://gitlab.com/api/v4/projects/acme%2Fwidgets/repository/branches?per_page=100"
        return httpx.Response(200, json=[{"name": "main", "commit": {"id": "sha1"}}])

    monkeypatch.setattr(git_hosting, "_client", _client_with(handler))
    branches = git_hosting.list_branches_gitlab(token="t", base_url=None, full_name="acme/widgets")
    assert branches == [{"name": "main", "commit_sha": "sha1"}]


def test_list_tags_gitlab_maps_fields(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert "/repository/tags" in str(request.url)
        return httpx.Response(200, json=[{"name": "v2.0.0", "commit": {"id": "sha2"}}])

    monkeypatch.setattr(git_hosting, "_client", _client_with(handler))
    tags = git_hosting.list_tags_gitlab(token="t", base_url=None, full_name="acme/widgets")
    assert tags == [{"name": "v2.0.0", "commit_sha": "sha2"}]


def test_list_commits_gitlab_maps_fields(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert "/repository/commits" in str(request.url)
        return httpx.Response(200, json=[{"id": "sha3", "title": "Fix the bug", "committed_date": "2026-01-01T00:00:00Z"}])

    monkeypatch.setattr(git_hosting, "_client", _client_with(handler))
    commits = git_hosting.list_commits_gitlab(token="t", base_url=None, full_name="acme/widgets")
    assert commits == [{"sha": "sha3", "message": "Fix the bug", "author_date": "2026-01-01T00:00:00Z"}]


def test_list_branches_github_raises_invalid_credentials_on_401(monkeypatch):
    monkeypatch.setattr(git_hosting, "_client", _client_with(lambda r: httpx.Response(401, json={})))
    with pytest.raises(git_hosting.CredentialError) as exc_info:
        git_hosting.list_branches_github(token="bad", base_url=None, full_name="octocat/widgets")
    assert exc_info.value.code == "invalid_credentials"
