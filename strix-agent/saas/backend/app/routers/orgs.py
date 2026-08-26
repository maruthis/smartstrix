from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import models, schemas
from ..audit import record_audit as _record_audit
from ..deps import current_org, current_session, current_user, db_dep, require_admin
from ..time_utils import utcnow

router = APIRouter(prefix="/api/orgs", tags=["orgs"])


class CreateOrgIn(BaseModel):
    name: str


class RenameOrgIn(BaseModel):
    name: str


class DeleteOrgIn(BaseModel):
    confirm_name: str


@router.post("")
def create_org(
    body: CreateOrgIn,
    user: models.User = Depends(current_user),
    sess: models.Session_ = Depends(current_session),
    db: Session = Depends(db_dep),
) -> schemas.OrganizationOut:
    org = models.Organization(name=body.name.strip() or "Untitled")
    db.add(org)
    db.flush()
    db.add(models.Membership(org_id=org.id, user_id=user.id, role="admin"))
    db.add(models.PRReviewSettings(org_id=org.id))
    db.add(
        models.Subscription(
            org_id=org.id,
            plan="pro_trial",
            status="trialing",
            trial_ends_at=utcnow() + timedelta(days=7),
        )
    )
    # Switch the caller's active org to the one they just created — without
    # this, any caller other than the frontend's onboarding flow (which
    # happens to always follow up with an explicit switch-org call) would
    # get 400 no_active_org from the very next org-scoped request.
    sess.active_org_id = org.id
    db.commit()
    _record_audit(db, org.id, user.id, "org.created", org.name)
    return schemas.OrganizationOut.model_validate(org)


@router.get("/current")
def get_current_org(org: models.Organization = Depends(current_org)) -> schemas.OrganizationOut:
    return schemas.OrganizationOut.model_validate(org)


@router.patch("/current")
def rename_org(
    body: RenameOrgIn,
    org: models.Organization = Depends(current_org),
    user: models.User = Depends(current_user),
    _admin=Depends(require_admin),
    db: Session = Depends(db_dep),
) -> schemas.OrganizationOut:
    org.name = body.name.strip() or org.name
    db.commit()
    _record_audit(db, org.id, user.id, "org.renamed", org.name)
    return schemas.OrganizationOut.model_validate(org)


@router.delete("/current")
def delete_org(
    body: DeleteOrgIn,
    org: models.Organization = Depends(current_org),
    _admin=Depends(require_admin),
    db: Session = Depends(db_dep),
) -> dict:
    if body.confirm_name != org.name:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="name_confirmation_mismatch")
    db.delete(org)
    db.commit()
    return {"ok": True}
