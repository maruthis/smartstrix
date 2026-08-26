from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import models
from ..audit import record_audit as _record_audit
from ..deps import current_org, current_user, db_dep, require_admin
from ..public_hosts import assert_public_https_url

router = APIRouter(prefix="/api/settings/webhooks", tags=["settings"])


def _serialize(w: models.Webhook) -> dict:
    # `secret` is deliberately omitted here: any member can list webhooks
    # (so they can see what's configured), but the signing secret is only
    # ever handed back once, in the create response below — the same
    # "shown once" pattern api_tokens uses for the raw token.
    return {
        "id": w.id,
        "url": w.url,
        "events": w.events,
        "status": w.status,
        "created_at": w.created_at.isoformat(),
    }


@router.get("")
def list_webhooks(org: models.Organization = Depends(current_org), db: Session = Depends(db_dep)) -> list[dict]:
    webhooks = db.query(models.Webhook).filter_by(org_id=org.id).all()
    return [_serialize(w) for w in webhooks]


class NewWebhookIn(BaseModel):
    url: str
    events: list[str] = ["pentest.completed", "issue.created", "pr_review.completed"]


@router.post("")
def create_webhook(
    body: NewWebhookIn,
    org: models.Organization = Depends(current_org),
    user: models.User = Depends(current_user),
    _admin=Depends(require_admin),
    db: Session = Depends(db_dep),
) -> dict:
    url = assert_public_https_url(body.url)
    webhook = models.Webhook(org_id=org.id, url=url, events=body.events)
    db.add(webhook)
    db.commit()
    _record_audit(db, org.id, user.id, "webhook.created", webhook.url, {"events": webhook.events})
    return {**_serialize(webhook), "secret": webhook.secret}


@router.delete("/{webhook_id}")
def delete_webhook(
    webhook_id: str,
    org: models.Organization = Depends(current_org),
    user: models.User = Depends(current_user),
    _admin=Depends(require_admin),
    db: Session = Depends(db_dep),
) -> dict:
    webhook = db.get(models.Webhook, webhook_id)
    if not webhook or webhook.org_id != org.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="not_found")
    url = webhook.url
    db.delete(webhook)
    db.commit()
    _record_audit(db, org.id, user.id, "webhook.deleted", url)
    return {"ok": True}
