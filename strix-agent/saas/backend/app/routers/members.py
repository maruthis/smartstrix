from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from .. import models, schemas
from ..deps import current_org, current_user, db_dep, require_admin
from ..settings import settings
from ..time_utils import utcnow
from ..audit import record_audit as _record_audit

router = APIRouter(prefix="/api/members", tags=["members"])


class InviteIn(BaseModel):
    email: EmailStr
    role: str = "member"


class RoleUpdateIn(BaseModel):
    role: str


@router.get("")
def list_members(org: models.Organization = Depends(current_org), db: Session = Depends(db_dep)) -> list[schemas.MembershipOut]:
    memberships = db.query(models.Membership).filter_by(org_id=org.id).all()
    return [schemas.MembershipOut.model_validate(m) for m in memberships]


@router.get("/invitations")
def list_invitations(org: models.Organization = Depends(current_org), db: Session = Depends(db_dep)) -> list[dict]:
    invites = (
        db.query(models.Invitation)
        .filter_by(org_id=org.id, accepted_at=None)
        .order_by(models.Invitation.created_at.desc())
        .all()
    )
    return [
        {"id": i.id, "email": i.email, "role": i.role, "created_at": i.created_at.isoformat()}
        for i in invites
    ]


@router.post("/invitations")
def create_invitation(
    body: InviteIn,
    org: models.Organization = Depends(current_org),
    user: models.User = Depends(current_user),
    _admin=Depends(require_admin),
    db: Session = Depends(db_dep),
) -> dict:
    existing_user = db.query(models.User).filter_by(email=body.email.lower()).first()
    if existing_user and db.query(models.Membership).filter_by(org_id=org.id, user_id=existing_user.id).first():
        raise HTTPException(status.HTTP_409_CONFLICT, detail="already_a_member")

    invite = models.Invitation(org_id=org.id, email=body.email.lower(), role=body.role)
    db.add(invite)
    db.commit()
    _record_audit(db, org.id, user.id, "member.invited", invite.email, {"role": invite.role})
    result: dict = {"ok": True, "invitation_id": invite.id}
    if settings.dev_mode:
        # No email provider wired up (see CONFIG.md) — in dev mode the
        # invitation token is returned directly so the accept flow is
        # testable. Gated the same way otp_start's dev_code is: never
        # leak a bearer credential in a real deployment.
        result["dev_accept_token"] = invite.token
    return result


@router.post("/invitations/{invitation_id}/revoke")
def revoke_invitation(
    invitation_id: str,
    org: models.Organization = Depends(current_org),
    _admin=Depends(require_admin),
    db: Session = Depends(db_dep),
) -> dict:
    invite = db.get(models.Invitation, invitation_id)
    if not invite or invite.org_id != org.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="not_found")
    db.delete(invite)
    db.commit()
    return {"ok": True}


class AcceptInvitationIn(BaseModel):
    token: str


@router.post("/invitations/accept")
def accept_invitation(
    body: AcceptInvitationIn,
    user: models.User = Depends(current_user),
    db: Session = Depends(db_dep),
) -> schemas.MembershipOut:
    invite = db.query(models.Invitation).filter_by(token=body.token, accepted_at=None).first()
    if not invite:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="invalid_or_used_invitation")
    if invite.expires_at < utcnow():
        raise HTTPException(status.HTTP_410_GONE, detail="invitation_expired")
    if invite.email != user.email.lower():
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="invitation_email_mismatch")

    invite.accepted_at = utcnow()
    membership = models.Membership(org_id=invite.org_id, user_id=user.id, role=invite.role)
    db.add(membership)
    db.commit()
    return schemas.MembershipOut.model_validate(membership)


@router.patch("/{member_user_id}")
def update_role(
    member_user_id: str,
    body: RoleUpdateIn,
    org: models.Organization = Depends(current_org),
    user: models.User = Depends(current_user),
    _admin=Depends(require_admin),
    db: Session = Depends(db_dep),
) -> schemas.MembershipOut:
    membership = db.query(models.Membership).filter_by(org_id=org.id, user_id=member_user_id).first()
    if not membership:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="not_found")
    membership.role = body.role
    db.commit()
    _record_audit(db, org.id, user.id, "member.role_updated", membership.user.email, {"role": body.role})
    return schemas.MembershipOut.model_validate(membership)


@router.delete("/{member_user_id}")
def remove_member(
    member_user_id: str,
    org: models.Organization = Depends(current_org),
    user: models.User = Depends(current_user),
    _admin=Depends(require_admin),
    db: Session = Depends(db_dep),
) -> dict:
    membership = db.query(models.Membership).filter_by(org_id=org.id, user_id=member_user_id).first()
    if not membership:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="not_found")
    email = membership.user.email
    db.delete(membership)
    db.commit()
    _record_audit(db, org.id, user.id, "member.removed", email)
    return {"ok": True}
