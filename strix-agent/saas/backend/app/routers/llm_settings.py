from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import crypto, models
from ..deps import current_org, current_user, db_dep, require_admin
from ..audit import record_audit as _record_audit

router = APIRouter(prefix="/api/settings/llm", tags=["settings"])


def _get_or_create(db: Session, org_id: str) -> models.OrgLlmSettings:
    row = db.get(models.OrgLlmSettings, org_id)
    if not row:
        row = models.OrgLlmSettings(org_id=org_id)
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def _serialize(row: models.OrgLlmSettings) -> dict:
    api_key = crypto.decrypt_or_legacy_plaintext(row.api_key)
    return {
        "model": row.model,
        "api_base": row.api_base,
        "api_key_set": bool(row.api_key),
        "api_key_last4": api_key[-4:] if api_key else None,
        "updated_at": row.updated_at.isoformat(),
    }


@router.get("")
def get_llm_settings(org: models.Organization = Depends(current_org), db: Session = Depends(db_dep)) -> dict:
    return _serialize(_get_or_create(db, org.id))


class UpdateLlmSettingsIn(BaseModel):
    model: str | None = None
    api_base: str | None = None
    # Omit or send an empty string to leave the existing key unchanged;
    # there is no bearer-token-style "shown once" flow for this since the
    # key is used server-side only and never round-tripped to the browser.
    api_key: str | None = None
    clear_api_key: bool = False


@router.patch("")
def update_llm_settings(
    body: UpdateLlmSettingsIn,
    org: models.Organization = Depends(current_org),
    user: models.User = Depends(current_user),
    _admin=Depends(require_admin),
    db: Session = Depends(db_dep),
) -> dict:
    row = _get_or_create(db, org.id)
    if body.model is not None:
        row.model = body.model.strip()
    if body.api_base is not None:
        row.api_base = body.api_base.strip() or None
    if body.clear_api_key:
        row.api_key = None
    elif body.api_key:
        row.api_key = crypto.encrypt(body.api_key.strip())
    db.commit()
    db.refresh(row)
    _record_audit(db, org.id, user.id, "llm_settings.updated", row.model or "(unset)", {"api_key_set": bool(row.api_key)})
    return _serialize(row)
