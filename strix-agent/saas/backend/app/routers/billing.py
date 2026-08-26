from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import models
from ..audit import record_audit as _record_audit
from ..deps import current_org, current_user, require_admin, db_dep
from ..providers import get_billing_provider

router = APIRouter(prefix="/api/settings/billing", tags=["settings"])


def _serialize(sub: models.Subscription) -> dict:
    return {
        "plan": sub.plan,
        "status": sub.status,
        "trial_ends_at": sub.trial_ends_at.isoformat() if sub.trial_ends_at else None,
        "card_added": sub.card_added,
        "current_period_end": sub.current_period_end.isoformat() if sub.current_period_end else None,
    }


def _get_or_create_subscription(db: Session, org_id: str) -> models.Subscription:
    sub = db.get(models.Subscription, org_id)
    if not sub:
        sub = models.Subscription(org_id=org_id)
        db.add(sub)
        db.commit()
        db.refresh(sub)
    return sub


@router.get("")
def get_billing(org: models.Organization = Depends(current_org), db: Session = Depends(db_dep)) -> dict:
    sub = _get_or_create_subscription(db, org.id)
    return _serialize(sub)


@router.post("/add-card")
def add_card(
    org: models.Organization = Depends(current_org),
    user: models.User = Depends(current_user),
    _admin=Depends(require_admin),
    db: Session = Depends(db_dep),
) -> dict:
    provider = get_billing_provider()
    try:
        provider.attach_card(org_id=org.id)
    except NotImplementedError as exc:
        # RealStripeProvider is scaffolded but not implemented yet (see
        # providers/billing.py) — surface a clear error instead of a 500
        # once a real Stripe key is configured.
        raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, detail="billing_provider_not_fully_configured") from exc
    sub = _get_or_create_subscription(db, org.id)
    sub.card_added = True
    sub.status = "active"
    db.commit()
    _record_audit(db, org.id, user.id, "billing.card_added", org.name)
    return _serialize(sub)


@router.get("/invoices")
def list_invoices(org: models.Organization = Depends(current_org), db: Session = Depends(db_dep)) -> list[dict]:
    provider = get_billing_provider()
    try:
        return provider.list_invoices(org_id=org.id)
    except NotImplementedError as exc:
        raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, detail="billing_provider_not_fully_configured") from exc
