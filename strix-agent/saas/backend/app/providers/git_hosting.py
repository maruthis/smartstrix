"""Real, per-org GitHub/GitLab connections authenticated with a
user-supplied Personal/Project Access Token (+ optional self-hosted base
URL) — this is what backs the "Connect" flow on Settings > Integrations
and the Repositories "Add Repository" picker.

This is deliberately separate from `providers/github.py`'s `RealGitHubProvider`,
which scaffolds a *different*, still-unimplemented model (a GitHub App
registered once for the whole deployment, used for PR-review check-runs
and webhooks). Here, credentials are per-org and per-token, which is the
right fit for a multi-tenant product and needs no app registration at
all — the tradeoff is the caller manages their own token instead of an
OAuth consent screen. Posting check-runs/PR comments and webhooks are out
of scope for this path for now; see saas/TASKS.md.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

import httpx

GITHUB_DEFAULT_API_BASE = "https://api.github.com"
GITLAB_DEFAULT_API_BASE = "https://gitlab.com/api/v4"

_TIMEOUT = 10.0


class CredentialError(Exception):
    """Raised when a token/URL/username combination can't authenticate,
    or the provider can't be reached at all. `code` is a stable machine
    detail string for the API response."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _client() -> httpx.Client:
    # A thin seam so tests can inject an httpx.MockTransport instead of
    # making real network calls, while production code takes the default
    # real-network client.
    return httpx.Client(timeout=_TIMEOUT)


def _get(url: str, headers: dict[str, str]) -> httpx.Response:
    try:
        with _client() as client:
            res = client.get(url, headers=headers)
    except httpx.RequestError as exc:
        raise CredentialError("provider_unreachable") from exc
    if res.status_code in (401, 403):
        raise CredentialError("invalid_credentials")
    if res.status_code >= 400:
        raise CredentialError("provider_error")
    return res


def _get_json(url: str, headers: dict[str, str]) -> Any:
    return _get(url, headers).json()


# Repo-listing calls page through every result rather than stopping at
# whatever the provider's default page size returns — a token with more
# than one page of accessible repos was silently missing everything past
# page 1 from the "Add Repository" picker. Capped so a runaway pagination
# loop (e.g. a provider that never signals "last page") can't hang a
# request forever; at per_page=100 this covers up to 2000 repos, which
# comfortably covers even a large enterprise account.
_MAX_PAGES = 20


def _get_all_pages_github(url: str, headers: dict[str, str]) -> list[Any]:
    """Follows GitHub's ``Link: <url>; rel="next"`` pagination header."""
    items: list[Any] = []
    next_url: str | None = url
    for _ in range(_MAX_PAGES):
        if next_url is None:
            break
        res = _get(next_url, headers)
        items.extend(res.json())
        next_url = res.links.get("next", {}).get("url")
    return items


def _get_all_pages_gitlab(url: str, headers: dict[str, str]) -> list[Any]:
    """Follows GitLab's page-number pagination via the ``X-Next-Page``
    response header (empty/absent once there's no next page)."""
    items: list[Any] = []
    page = 1
    for _ in range(_MAX_PAGES):
        res = _get(f"{url}&page={page}", headers)
        items.extend(res.json())
        next_page = res.headers.get("X-Next-Page")
        if not next_page:
            break
        page = int(next_page)
    return items


def _github_api_base(base_url: str | None) -> str:
    return f"{base_url.rstrip('/')}/api/v3" if base_url else GITHUB_DEFAULT_API_BASE


def _github_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}


def verify_github(*, token: str, base_url: str | None) -> str:
    """Confirms the token authenticates, and returns the GitHub login it belongs to."""
    data = _get_json(f"{_github_api_base(base_url)}/user", _github_headers(token))
    return data["login"]


def list_repos_github(*, token: str, base_url: str | None) -> list[dict[str, Any]]:
    url = f"{_github_api_base(base_url)}/user/repos?per_page=100&affiliation=owner,collaborator,organization_member"
    data = _get_all_pages_github(url, _github_headers(token))
    return [
        {"full_name": r["full_name"], "default_branch": r.get("default_branch") or "main", "private": bool(r.get("private"))}
        for r in data
    ]


def list_branches_github(*, token: str, base_url: str | None, full_name: str) -> list[dict[str, Any]]:
    url = f"{_github_api_base(base_url)}/repos/{full_name}/branches?per_page=100"
    data = _get_json(url, _github_headers(token))
    return [{"name": b["name"], "commit_sha": b["commit"]["sha"]} for b in data]


def list_tags_github(*, token: str, base_url: str | None, full_name: str) -> list[dict[str, Any]]:
    url = f"{_github_api_base(base_url)}/repos/{full_name}/tags?per_page=100"
    data = _get_json(url, _github_headers(token))
    return [{"name": t["name"], "commit_sha": t["commit"]["sha"]} for t in data]


def list_commits_github(*, token: str, base_url: str | None, full_name: str) -> list[dict[str, Any]]:
    url = f"{_github_api_base(base_url)}/repos/{full_name}/commits?per_page=50"
    data = _get_json(url, _github_headers(token))
    return [
        {
            "sha": c["sha"],
            "message": (c.get("commit", {}).get("message") or "").split("\n", 1)[0],
            "author_date": c.get("commit", {}).get("author", {}).get("date"),
        }
        for c in data
    ]


def list_pull_requests_github(*, token: str, base_url: str | None, full_name: str) -> list[dict[str, Any]]:
    url = f"{_github_api_base(base_url)}/repos/{full_name}/pulls?state=open&per_page=100"
    data = _get_all_pages_github(url, _github_headers(token))
    return [
        {
            "number": p["number"],
            "title": p["title"],
            "author": (p.get("user") or {}).get("login") or "unknown",
            "source_branch": (p.get("head") or {}).get("ref"),
            "target_branch": (p.get("base") or {}).get("ref"),
            "url": p.get("html_url"),
        }
        for p in data
    ]


def _gitlab_api_base(base_url: str | None) -> str:
    return f"{base_url.rstrip('/')}/api/v4" if base_url else GITLAB_DEFAULT_API_BASE


def _gitlab_headers(token: str) -> dict[str, str]:
    return {"PRIVATE-TOKEN": token}


def verify_gitlab(*, token: str, base_url: str | None) -> str:
    """Confirms the token authenticates, and returns the GitLab username it belongs to."""
    data = _get_json(f"{_gitlab_api_base(base_url)}/user", _gitlab_headers(token))
    return data["username"]


def list_repos_gitlab(*, token: str, base_url: str | None) -> list[dict[str, Any]]:
    url = f"{_gitlab_api_base(base_url)}/projects?membership=true&per_page=100"
    data = _get_all_pages_gitlab(url, _gitlab_headers(token))
    return [
        {
            "full_name": p["path_with_namespace"],
            "default_branch": p.get("default_branch") or "main",
            "private": p.get("visibility") != "public",
        }
        for p in data
    ]


def _gitlab_project_id(full_name: str) -> str:
    # GitLab's REST API accepts a URL-encoded "namespace/path" in place of
    # the numeric project id.
    return quote(full_name, safe="")


def list_branches_gitlab(*, token: str, base_url: str | None, full_name: str) -> list[dict[str, Any]]:
    url = f"{_gitlab_api_base(base_url)}/projects/{_gitlab_project_id(full_name)}/repository/branches?per_page=100"
    data = _get_json(url, _gitlab_headers(token))
    return [{"name": b["name"], "commit_sha": b["commit"]["id"]} for b in data]


def list_tags_gitlab(*, token: str, base_url: str | None, full_name: str) -> list[dict[str, Any]]:
    url = f"{_gitlab_api_base(base_url)}/projects/{_gitlab_project_id(full_name)}/repository/tags?per_page=100"
    data = _get_json(url, _gitlab_headers(token))
    return [{"name": t["name"], "commit_sha": t["commit"]["id"]} for t in data]


def list_commits_gitlab(*, token: str, base_url: str | None, full_name: str) -> list[dict[str, Any]]:
    url = f"{_gitlab_api_base(base_url)}/projects/{_gitlab_project_id(full_name)}/repository/commits?per_page=50"
    data = _get_json(url, _gitlab_headers(token))
    return [
        {"sha": c["id"], "message": (c.get("title") or ""), "author_date": c.get("committed_date")} for c in data
    ]


def list_pull_requests_gitlab(*, token: str, base_url: str | None, full_name: str) -> list[dict[str, Any]]:
    """GitLab's merge requests are the equivalent of GitHub's pull requests.
    ``iid`` (not the global ``id``) is the project-scoped number shown in
    the UI/URL (``!42``) — the right analog to GitHub's ``number``."""
    url = f"{_gitlab_api_base(base_url)}/projects/{_gitlab_project_id(full_name)}/merge_requests?state=opened&scope=all&per_page=100"
    data = _get_all_pages_gitlab(url, _gitlab_headers(token))
    return [
        {
            "number": mr["iid"],
            "title": mr["title"],
            "author": (mr.get("author") or {}).get("username") or "unknown",
            "source_branch": mr.get("source_branch"),
            "target_branch": mr.get("target_branch"),
            "url": mr.get("web_url"),
        }
        for mr in data
    ]
