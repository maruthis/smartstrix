from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import crypto, models
from ..audit import record_audit as _record_audit
from ..deps import current_org, current_user, db_dep, require_admin
from ..llm_probe import LlmConnectionError, probe_llm_connection

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


class ValidateLlmSettingsIn(BaseModel):
    model: str = ""
    api_base: str | None = None
    # Omit or send an empty string to use the key already stored for this org.
    api_key: str | None = None


def _resolve_probe_key(body: ValidateLlmSettingsIn, row: models.OrgLlmSettings) -> str:
    if body.api_key and body.api_key.strip():
        return body.api_key.strip()
    stored = crypto.decrypt_or_legacy_plaintext(row.api_key) if row.api_key else None
    if stored:
        return stored
    raise HTTPException(
        status.HTTP_400_BAD_REQUEST,
        detail="Enter an API key to verify this provider.",
    )


@router.post("/validate")
def validate_llm_settings(
    body: ValidateLlmSettingsIn,
    org: models.Organization = Depends(current_org),
    _admin=Depends(require_admin),
    db: Session = Depends(db_dep),
) -> dict:
    model = (body.model or "").strip()
    if not model:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Enter a model name to verify the connection.",
        )
    row = _get_or_create(db, org.id)
    api_key = _resolve_probe_key(body, row)
    api_base = body.api_base.strip() if body.api_base and body.api_base.strip() else None
    try:
        probe_llm_connection(model=model, api_key=api_key, api_base=api_base)
    except LlmConnectionError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {"ok": True, "message": "Connection verified. You can save these settings."}


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
