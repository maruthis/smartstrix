"""Third-party integrations (source control, chat, issue tracking).

For GitHub and GitLab, "Connect" is a *real* integration: the caller
supplies a Personal/Project Access Token (+ optional self-hosted base URL
for GitLab, or a GitHub Enterprise Server URL), which is verified live
against the provider's API before it's saved — see `providers/git_hosting.py`.
The full token is encrypted at rest (`app/crypto.py`) so it can be decrypted
later to make real API calls (e.g. listing real repos, see
`routers/repositories.py`'s `list_installable`); only its last 4 characters
are additionally kept as plaintext for display.

The other providers (Bitbucket, Slack, Jira, Linear) don't have a live
call wired up yet — connecting them is a real per-org DB write, but
there's no OAuth handshake or API verification behind it, since that
needs a registered app with each provider that only the operator of a
deployment can create (see CONFIG.md for the same tradeoff already made
for the GitHub App and Stripe integrations).

`configure_url` in the catalog is a real, provider-owned settings page
that the frontend opens in a new tab from the "Configure" action — for a
GitHub-App-style installation, that's e.g. the "Installed GitHub Apps"
list. github/gitlab deliberately have no `configure_url`: they're a
per-org access token, not an app installation, so there's nothing on the
provider's side to configure once connected (disconnecting/reconnecting
happens entirely in this UI).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import crypto, models
from ..deps import current_org, current_user, db_dep, require_admin
from ..providers import git_hosting
from ..audit import record_audit as _record_audit

router = APIRouter(prefix="/api/integrations", tags=["integrations"])

CATALOG = [
    # No configure_url for github/gitlab: those settings pages are for a
    # GitHub-App-style installation, which this integration isn't — it's a
    # per-org personal/project access token (see git_hosting.py's
    # docstring), so there's nothing on the provider's side to configure.
    {"provider": "github", "category": "code", "label": "GitHub", "live": True},
    {"provider": "gitlab", "category": "code", "label": "GitLab", "live": True},
    {"provider": "bitbucket", "category": "code", "label": "Bitbucket"},
    {"provider": "slack", "category": "communication", "label": "Slack"},
    {"provider": "msteams", "category": "communication", "label": "Microsoft Teams", "coming_soon": True},
    {"provider": "jira", "category": "issue_tracking", "label": "Jira"},
    {"provider": "linear", "category": "issue_tracking", "label": "Linear"},
]
CATALOG_BY_PROVIDER = {c["provider"]: c for c in CATALOG}
_LIVE_PROVIDERS = {c["provider"] for c in CATALOG if c.get("live")}


def _verify_live(provider: str, *, token: str, base_url: str | None) -> str:
    # Looked up on `git_hosting` by attribute at call time (not bound into
    # a dict at import time) so tests can monkeypatch git_hosting.verify_*.
    return getattr(git_hosting, f"verify_{provider}")(token=token, base_url=base_url)


def _list_live(provider: str, *, token: str, base_url: str | None) -> list[dict]:
    return getattr(git_hosting, f"list_repos_{provider}")(token=token, base_url=base_url)


def _serialize(entry: dict, integration: models.Integration | None) -> dict:
    return {
        "provider": entry["provider"],
        "category": entry["category"],
        "label": entry["label"],
        "coming_soon": entry.get("coming_soon", False),
        "live": entry.get("live", False),
        "configure_url": entry.get("configure_url"),
        "status": "connected" if integration else "not_connected",
        "account_label": integration.account_label if integration else None,
        "base_url": integration.base_url if integration else None,
        "credential_last4": integration.credential_last4 if integration else None,
        "connected_at": integration.connected_at.isoformat() if integration else None,
    }


@router.get("")
def list_integrations(org: models.Organization = Depends(current_org), db: Session = Depends(db_dep)) -> list[dict]:
    rows = {i.provider: i for i in db.query(models.Integration).filter_by(org_id=org.id).all()}
    return [_serialize(entry, rows.get(entry["provider"])) for entry in CATALOG]


class ConnectIn(BaseModel):
    account_label: str
    credential: str | None = None
    base_url: str | None = None


@router.post("/{provider}/connect")
def connect_integration(
    provider: str,
    body: ConnectIn,
    org: models.Organization = Depends(current_org),
    user: models.User = Depends(current_user),
    db: Session = Depends(db_dep),
    _admin=Depends(require_admin),
) -> dict:
    entry = CATALOG_BY_PROVIDER.get(provider)
    if not entry:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="unknown_provider")
    if entry.get("coming_soon"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="provider_not_yet_available")

    account_label = body.account_label.strip()
    if not account_label:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="account_label_required")
    credential = (body.credential or "").strip()
    base_url = (body.base_url or "").strip() or None

    if entry.get("live"):
        # GitHub/GitLab are real integrations: a token is required and
        # verified live against the provider before anything is saved, so
        # a bad token/URL fails loudly right away instead of silently on
        # the next scan.
        if not credential:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="credential_required")
        try:
            _verify_live(provider, token=credential, base_url=base_url)
        except git_hosting.CredentialError as exc:
            code = {"invalid_credentials": status.HTTP_401_UNAUTHORIZED, "provider_unreachable": status.HTTP_502_BAD_GATEWAY}.get(
                exc.code, status.HTTP_502_BAD_GATEWAY
            )
            raise HTTPException(code, detail=exc.code) from exc

    credential_last4 = credential[-4:] if credential else None
    credential_encrypted = crypto.encrypt(credential) if credential else None

    integration = db.query(models.Integration).filter_by(org_id=org.id, provider=provider).first()
    if integration:
        integration.account_label = account_label
        integration.base_url = base_url
        integration.credential_encrypted = credential_encrypted
        integration.credential_last4 = credential_last4
    else:
        integration = models.Integration(
            org_id=org.id,
            provider=provider,
            account_label=account_label,
            base_url=base_url,
            credential_encrypted=credential_encrypted,
            credential_last4=credential_last4,
        )
        db.add(integration)
    db.commit()
    db.refresh(integration)
    _record_audit(db, org.id, user.id, "integration.connected", entry["label"], {"account_label": account_label})
    return _serialize(entry, integration)


def list_live_repos(db: Session, org_id: str, provider: str) -> list[dict] | None:
    """Real repos for a connected github/gitlab integration that has a
    stored credential. Returns None when there's nothing to call live —
    the provider isn't github/gitlab, isn't connected, or (like the
    seeded demo integration) is connected without a credential — so the
    caller can fall back to the mock catalog. Raises HTTPException
    (401/502) if the stored credential no longer works."""
    if provider not in _LIVE_PROVIDERS:
        return None
    integration = db.query(models.Integration).filter_by(org_id=org_id, provider=provider).first()
    if not integration or not integration.credential_encrypted:
        return None
    token = crypto.decrypt(integration.credential_encrypted)
    try:
        return _list_live(provider, token=token, base_url=integration.base_url)
    except git_hosting.CredentialError as exc:
        code = {"invalid_credentials": status.HTTP_401_UNAUTHORIZED, "provider_unreachable": status.HTTP_502_BAD_GATEWAY}.get(
            exc.code, status.HTTP_502_BAD_GATEWAY
        )
        raise HTTPException(code, detail=exc.code) from exc


REF_TYPES = ("branches", "tags", "commits")


def list_live_refs(db: Session, org_id: str, repo: models.Repository, ref_type: str) -> list[dict]:
    """Branches/tags/commits for `repo` from its connected github/gitlab
    integration's stored credential — the picklist behind the New Pentest
    branch/tag/commit selector, so a pentest targets a real, existing ref
    instead of a hand-typed name that might not exist. Unlike
    `list_live_repos`, there's no mock fallback: without a live,
    credentialed integration there's nothing to list, so this returns []
    rather than a fake catalog (the caller falls back to the repository's
    plain default_branch when nothing is selected either way)."""
    if repo.provider not in _LIVE_PROVIDERS or ref_type not in REF_TYPES:
        return []
    integration = db.query(models.Integration).filter_by(org_id=org_id, provider=repo.provider).first()
    if not integration or not integration.credential_encrypted:
        return []
    token = crypto.decrypt(integration.credential_encrypted)
    try:
        fn = getattr(git_hosting, f"list_{ref_type}_{repo.provider}")
        return fn(token=token, base_url=integration.base_url, full_name=repo.full_name)
    except git_hosting.CredentialError as exc:
        code = {"invalid_credentials": status.HTTP_401_UNAUTHORIZED, "provider_unreachable": status.HTTP_502_BAD_GATEWAY}.get(
            exc.code, status.HTTP_502_BAD_GATEWAY
        )
        raise HTTPException(code, detail=exc.code) from exc


def list_live_pull_requests(db: Session, org_id: str, repo: models.Repository) -> list[dict]:
    """Open pull/merge requests for `repo` from its connected github/gitlab
    integration's stored credential — backs the PR picker on "Review a
    Pull Request", so a review targets a real, existing PR instead of a
    hand-typed number/title. Same no-mock-fallback contract as
    `list_live_refs`: without a live, credentialed integration this
    returns [] and the caller falls back to manual entry."""
    if repo.provider not in _LIVE_PROVIDERS:
        return []
    integration = db.query(models.Integration).filter_by(org_id=org_id, provider=repo.provider).first()
    if not integration or not integration.credential_encrypted:
        return []
    token = crypto.decrypt(integration.credential_encrypted)
    try:
        fn = getattr(git_hosting, f"list_pull_requests_{repo.provider}")
        return fn(token=token, base_url=integration.base_url, full_name=repo.full_name)
    except git_hosting.CredentialError as exc:
        code = {"invalid_credentials": status.HTTP_401_UNAUTHORIZED, "provider_unreachable": status.HTTP_502_BAD_GATEWAY}.get(
            exc.code, status.HTTP_502_BAD_GATEWAY
        )
        raise HTTPException(code, detail=exc.code) from exc


@router.delete("/{provider}")
def disconnect_integration(
    provider: str,
    org: models.Organization = Depends(current_org),
    user: models.User = Depends(current_user),
    db: Session = Depends(db_dep),
    _admin=Depends(require_admin),
) -> dict:
    entry = CATALOG_BY_PROVIDER.get(provider)
    if not entry:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="unknown_provider")

    integration = db.query(models.Integration).filter_by(org_id=org.id, provider=provider).first()
    if integration:
        db.delete(integration)
        db.commit()
        _record_audit(db, org.id, user.id, "integration.disconnected", entry["label"])
    return _serialize(entry, None)
