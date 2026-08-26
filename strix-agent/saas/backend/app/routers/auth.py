from __future__ import annotations

import secrets
import string
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from .. import models, schemas
from ..audit import record_audit as _record_audit
from ..deps import CSRF_COOKIE_NAME, csrf_for_session, current_session, current_user, db_dep
from ..settings import settings
from ..time_utils import utcnow

router = APIRouter(prefix="/api/auth", tags=["auth"])

OTP_TTL_MINUTES = 10
MAX_OTP_ATTEMPTS = 5
MAX_OTP_STARTS_PER_WINDOW = 5
OTP_START_WINDOW = timedelta(minutes=OTP_TTL_MINUTES)
# Absolute session lifetime — shared by the cookie's max_age (client-side
# only, and easily stripped/edited) and Session_.expires_at (server-side,
# what actually matters). A leaked token stops working after this long
# even if the cookie is replayed with its max_age intact.
SESSION_TTL = timedelta(days=30)


class OtpStartIn(BaseModel):
    email: EmailStr


class OtpVerifyIn(BaseModel):
    email: EmailStr
    code: str


class SwitchOrgIn(BaseModel):
    org_id: str


def _set_session_cookie(response: Response, token: str) -> None:
    max_age = int(SESSION_TTL.total_seconds())
    response.set_cookie(
        settings.session_cookie_name,
        token,
        httponly=True,
        samesite="lax",
        secure=not settings.dev_mode,
        max_age=max_age,
    )
    response.set_cookie(
        CSRF_COOKIE_NAME,
        csrf_for_session(token),
        httponly=False,
        samesite="lax",
        secure=not settings.dev_mode,
        max_age=max_age,
    )


@router.post("/otp/start")
def otp_start(body: OtpStartIn, db: Session = Depends(db_dep)) -> dict:
    email = body.email.lower()
    window_start = utcnow() - OTP_START_WINDOW
    recent = (
        db.query(models.OtpCode)
        .filter(models.OtpCode.email == email, models.OtpCode.created_at >= window_start)
        .count()
    )
    if recent >= MAX_OTP_STARTS_PER_WINDOW:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, detail="too_many_otp_requests")
    code = "".join(secrets.choice(string.digits) for _ in range(6))
    db.add(
        models.OtpCode(
            email=email,
            code=code,
            expires_at=utcnow() + timedelta(minutes=OTP_TTL_MINUTES),
        )
    )
    db.commit()
    result: dict = {"ok": True}
    if settings.dev_mode:
        # No email provider wired up yet (see CONFIG.md) — dev mode hands
        # the code straight back so the OTP flow is testable end-to-end
        # without sending real email.
        result["dev_code"] = code
    return result


@router.post("/otp/verify")
def otp_verify(body: OtpVerifyIn, response: Response, db: Session = Depends(db_dep)) -> schemas.MeOut:
    email = body.email.lower()
    # Look up the latest *pending* code for this email regardless of what
    # was submitted (not filtered by code == body.code) — that's what lets
    # us count failed attempts against it and lock it out below. A 6-digit
    # code with unlimited guesses is brute-forceable within its TTL; this
    # caps it at MAX_OTP_ATTEMPTS tries per requested code.
    otp = (
        db.query(models.OtpCode)
        .filter(models.OtpCode.email == email, models.OtpCode.consumed.is_(False))
        .order_by(models.OtpCode.created_at.desc())
        .first()
    )
    if not otp or otp.expires_at < utcnow():
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="invalid_or_expired_code")
    if otp.attempts >= MAX_OTP_ATTEMPTS:
        otp.consumed = True
        db.commit()
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, detail="too_many_attempts")
    if otp.code != body.code:
        otp.attempts += 1
        db.commit()
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="invalid_or_expired_code")
    otp.consumed = True

    user = db.query(models.User).filter_by(email=email).first()
    if not user:
        user = models.User(email=email, name=email.split("@")[0])
        db.add(user)
        db.flush()

    membership = db.query(models.Membership).filter_by(user_id=user.id).first()
    session = models.Session_(
        user_id=user.id,
        active_org_id=membership.org_id if membership else None,
        expires_at=utcnow() + SESSION_TTL,
    )
    db.add(session)
    db.commit()

    _set_session_cookie(response, session.token)
    # Pre-auth events (OTP requested, wrong code, expired code) have no org
    # to scope an AuditLogEntry to — they're already covered by the
    # org-agnostic request log (any non-GET or error response is logged
    # there regardless of auth state). Once login succeeds and an org is
    # resolved, that's the first point an org-scoped audit entry makes sense.
    if session.active_org_id:
        _record_audit(db, session.active_org_id, user.id, "auth.login_succeeded", user.email)
    return _me_payload(db, user, session)


@router.post("/logout")
def logout(response: Response, sess: models.Session_ = Depends(current_session), user: models.User = Depends(current_user), db: Session = Depends(db_dep)) -> dict:
    active_org_id = sess.active_org_id
    db.delete(sess)
    db.commit()
    response.delete_cookie(settings.session_cookie_name)
    response.delete_cookie(CSRF_COOKIE_NAME)
    if active_org_id:
        _record_audit(db, active_org_id, user.id, "auth.logout", user.email)
    return {"ok": True}


@router.get("/me")
def me(
    user: models.User = Depends(current_user),
    sess: models.Session_ = Depends(current_session),
    db: Session = Depends(db_dep),
) -> schemas.MeOut:
    return _me_payload(db, user, sess)


@router.post("/switch-org")
def switch_org(
    body: SwitchOrgIn,
    user: models.User = Depends(current_user),
    sess: models.Session_ = Depends(current_session),
    db: Session = Depends(db_dep),
) -> schemas.MeOut:
    membership = db.query(models.Membership).filter_by(user_id=user.id, org_id=body.org_id).first()
    if not membership:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="not_a_member")
    sess.active_org_id = body.org_id
    db.commit()
    return _me_payload(db, user, sess)


def _me_payload(db: Session, user: models.User, sess: models.Session_) -> schemas.MeOut:
    memberships = db.query(models.Membership).filter_by(user_id=user.id).all()
    orgs = [db.get(models.Organization, m.org_id) for m in memberships]
    active_org = db.get(models.Organization, sess.active_org_id) if sess.active_org_id else None
    active_membership = next((m for m in memberships if m.org_id == sess.active_org_id), None)
    return schemas.MeOut(
        user=schemas.UserOut.model_validate(user),
        active_org=schemas.OrganizationOut.model_validate(active_org) if active_org else None,
        role=active_membership.role if active_membership else None,
        organizations=[schemas.OrganizationOut.model_validate(o) for o in orgs if o],
    )
