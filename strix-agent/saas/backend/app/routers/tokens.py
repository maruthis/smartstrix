from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import models
from ..deps import current_org, current_user, db_dep, require_admin
from ..time_utils import utcnow
from ..audit import record_audit as _record_audit

router = APIRouter(prefix="/api/settings/tokens", tags=["settings"])


def _serialize(t: models.ApiToken) -> dict:
    return {
        "id": t.id,
        "name": t.name,
        "token_type": t.token_type,
        "scopes": t.scopes,
        "token_prefix": t.token_prefix,
        "status": t.status,
        "last_used_at": t.last_used_at.isoformat() if t.last_used_at else None,
        "expires_at": t.expires_at.isoformat() if t.expires_at else None,
        "created_at": t.created_at.isoformat(),
    }


@router.get("")
def list_tokens(org: models.Organization = Depends(current_org), db: Session = Depends(db_dep)) -> list[dict]:
    tokens = db.query(models.ApiToken).filter_by(org_id=org.id).order_by(models.ApiToken.created_at.desc()).all()
    return [_serialize(t) for t in tokens]


class NewTokenIn(BaseModel):
    name: str
    token_type: str = "personal"
    scopes: list[str] = ["read"]
    expires_in_days: int | None = 90  # None = no expiration


@router.post("")
def create_token(
    body: NewTokenIn,
    org: models.Organization = Depends(current_org),
    user: models.User = Depends(current_user),
    _admin=Depends(require_admin),
    db: Session = Depends(db_dep),
) -> dict:
    # Admin-only: tokens aren't scoped to their creator (no user_id column),
    # so any token created is effectively an org-wide credential, and its
    # `scopes` are accepted as-is with no allow-list check against the
    # caller's own role — a non-admin could otherwise mint a token with
    # broader scopes (e.g. organizations:write) than they hold themselves.
    raw_token = f"strix_{secrets.token_urlsafe(32)}"
    token = models.ApiToken(
        org_id=org.id,
        name=body.name,
        token_type=body.token_type,
        scopes=body.scopes,
        token_hash=hashlib.sha256(raw_token.encode()).hexdigest(),
        token_prefix=raw_token[:12],
        expires_at=utcnow() + timedelta(days=body.expires_in_days) if body.expires_in_days else None,
    )
    db.add(token)
    db.commit()
    _record_audit(db, org.id, user.id, "api_token.created", token.name)
    return {**_serialize(token), "token": raw_token}


@router.delete("/{token_id}")
def revoke_token(
    token_id: str,
    org: models.Organization = Depends(current_org),
    user: models.User = Depends(current_user),
    _admin=Depends(require_admin),
    db: Session = Depends(db_dep),
) -> dict:
    # Admin-only: without this, any member could revoke another member's
    # (or an admin's, or CI's) token.
    token = db.get(models.ApiToken, token_id)
    if not token or token.org_id != org.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="not_found")
    token.status = "revoked"
    db.commit()
    _record_audit(db, org.id, user.id, "api_token.revoked", token.name)
    return {"ok": True}
