"""GitHub App integration behind a provider interface.

`MockGitHubProvider` is the default — it returns a fixed in-memory list of
"installable" repos and fakes PR/check-run/webhook operations, so the whole
Repositories + PR Reviews flow is fully clickable with zero setup.

`RealGitHubProvider` activates once `SAAS_GITHUB_APP_ID` and
`SAAS_GITHUB_APP_PRIVATE_KEY` are set (see ../../CONFIG.md). It is left as
a scaffold with the real GitHub API calls to fill in — App JWT signing,
installation-token exchange, and webhook signature verification are
well-documented GitHub App flows; wiring them up requires an actual
registered GitHub App (App ID, private key, webhook secret) which only the
operator of this deployment can create.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from ..settings import settings


class GitHubProvider(ABC):
    @abstractmethod
    def installable_repositories(self) -> list[dict[str, Any]]:
        """Repos available to add, as seen through the org's GitHub App installation(s)."""

    @abstractmethod
    def create_check_run(self, *, full_name: str, pr_number: int, conclusion: str, summary: str) -> dict[str, Any]:
        """Post a check-run/status to block or pass a PR."""

    @abstractmethod
    def post_pr_comment(self, *, full_name: str, pr_number: int, body: str) -> dict[str, Any]:
        """Comment findings on a PR."""

    @abstractmethod
    def verify_webhook_signature(self, *, payload: bytes, signature_header: str | None) -> bool:
        """Verify an inbound GitHub webhook's HMAC signature."""


class MockGitHubProvider(GitHubProvider):
    _CATALOG = [
        {"full_name": "maruthis/anything-llm", "default_branch": "main", "private": False},
        {"full_name": "maruthis/strix", "default_branch": "main", "private": False},
        {"full_name": "maruthis/example-api", "default_branch": "main", "private": True},
    ]

    def installable_repositories(self) -> list[dict[str, Any]]:
        return list(self._CATALOG)

    def create_check_run(self, *, full_name: str, pr_number: int, conclusion: str, summary: str) -> dict[str, Any]:
        return {"mock": True, "full_name": full_name, "pr_number": pr_number, "conclusion": conclusion, "summary": summary}

    def post_pr_comment(self, *, full_name: str, pr_number: int, body: str) -> dict[str, Any]:
        return {"mock": True, "full_name": full_name, "pr_number": pr_number, "body": body}

    def verify_webhook_signature(self, *, payload: bytes, signature_header: str | None) -> bool:
        # Mock mode has no real webhook secret; accept everything so local
        # testing (e.g. curl'ing the webhook endpoint) works out of the box.
        return True


class RealGitHubProvider(GitHubProvider):
    """Scaffold for a real GitHub App integration.

    Fill in with: JWT-signed App auth -> installation access token exchange
    (POST /app/installations/{id}/access_tokens), the GitHub REST API for
    check-runs/comments, and HMAC-SHA256 webhook verification against
    SAAS_GITHUB_WEBHOOK_SECRET. Requires `settings.github_app_id`,
    `settings.github_app_private_key`, `settings.github_webhook_secret`.
    """

    def installable_repositories(self) -> list[dict[str, Any]]:
        raise NotImplementedError("Real GitHub App integration not yet implemented; see class docstring.")

    def create_check_run(self, *, full_name: str, pr_number: int, conclusion: str, summary: str) -> dict[str, Any]:
        raise NotImplementedError

    def post_pr_comment(self, *, full_name: str, pr_number: int, body: str) -> dict[str, Any]:
        raise NotImplementedError

    def verify_webhook_signature(self, *, payload: bytes, signature_header: str | None) -> bool:
        import hashlib
        import hmac

        if not signature_header or not signature_header.startswith("sha256="):
            return False
        expected = hmac.new((settings.github_webhook_secret or "").encode(), payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(f"sha256={expected}", signature_header)


def get_github_provider() -> GitHubProvider:
    if settings.github_configured:
        return RealGitHubProvider()
    return MockGitHubProvider()
