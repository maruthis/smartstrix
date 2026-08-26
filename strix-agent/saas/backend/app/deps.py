from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from collections.abc import Generator

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from . import models
from .db import get_db
from .settings import settings
from .time_utils import utcnow


def db_dep() -> Generator[Session, None, None]:
    yield from get_db()


CSRF_COOKIE_NAME = "csrf_token"


@dataclass(frozen=True)
class AuthContext:
    org_id: str | None
    user_id: str | None
    membership_id: str | None
    role: str | None
    scopes: tuple[str, ...]
    is_api_token: bool = False


def csrf_for_session(token: str) -> str:
    return hmac.new(settings.session_secret.encode(), token.encode(), hashlib.sha256).hexdigest()


def _is_unsafe_method(method: str) -> bool:
    return method.upper() not in {"GET", "HEAD", "OPTIONS", "TRACE"}


def _enforce_csrf(request: Request, sess: models.Session_) -> None:
    if not _is_unsafe_method(request.method):
        return
    expected = csrf_for_session(sess.token)
    supplied = request.headers.get("x-csrf-token") or request.headers.get("x-xsrf-token")
    cookie = request.cookies.get(CSRF_COOKIE_NAME)
    if not supplied or not cookie or not hmac.compare_digest(supplied, expected) or not hmac.compare_digest(cookie, expected):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="csrf_failed")


def _scope_for_request(request: Request) -> str | None:
    path = request.url.path
    method = request.method.upper()
    write = method not in {"GET", "HEAD", "OPTIONS"}
    if path.startswith("/api/pentests") or path.startswith("/api/pentest-schedules"):
        return "scans:write" if write else "scans:read"
    if path.startswith("/api/pr-reviews"):
        return "pr_reviews:read" if not write else "scans:write"
    if path.startswith("/api/issues"):
        return "vulnerabilities:write" if write else "vulnerabilities:read"
    if path.startswith("/api/repositories") or path.startswith("/api/domains"):
        return "assets:write" if write else "assets:read"
    if path.startswith("/api/knowledge"):
        return "assets:write" if write else "assets:read"
    if path.startswith("/api/settings/tokens"):
        return "tokens:write" if write else "tokens:read"
    if path.startswith("/api/settings/webhooks"):
        return "webhooks:write" if write else "webhooks:read"
    if path.startswith("/api/audit"):
        return "audit:read"
    if path.startswith("/api/billing"):
        return "organizations:write" if write else "organizations:read"
    return None


def _scope_allowed(scopes: list | tuple[str, ...], required: str | None) -> bool:
    if required is None:
        return False
    scope_set = {str(scope) for scope in scopes}
    if "*" in scope_set or required in scope_set:
        return True
    namespace = required.split(":", 1)[0]
    return f"{namespace}:*" in scope_set


def _api_token_context(request: Request, db: Session) -> AuthContext | None:
    auth = request.headers.get("authorization", "")
    scheme, _, credential = auth.partition(" ")
    if scheme.lower() != "bearer" or not credential:
        return None
    token_hash = hashlib.sha256(credential.encode()).hexdigest()
    token = db.query(models.ApiToken).filter_by(token_hash=token_hash).first()
    if not token or token.status != "active":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="invalid_api_token")
    if token.expires_at is not None and token.expires_at < utcnow():
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="api_token_expired")
    required_scope = _scope_for_request(request)
    if not _scope_allowed(token.scopes or [], required_scope):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="insufficient_scope")
    token.last_used_at = utcnow()
    db.commit()
    return AuthContext(
        org_id=token.org_id,
        user_id=None,
        membership_id=None,
        role=None,
        scopes=tuple(str(scope) for scope in token.scopes or []),
        is_api_token=True,
    )


def current_session(request: Request, db: Session = Depends(db_dep)) -> models.Session_:
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="not_authenticated")
    sess = db.get(models.Session_, token)
    if not sess:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="not_authenticated")
    # expires_at is nullable only for a session row that predates this
    # column (see models.Session_) — those are treated as still valid
    # rather than immediately logged out, and simply age out the normal
    # way once the user re-authenticates. Every session created since
    # (see auth.py's otp_verify) always sets it, so this is a one-time
    # adoption allowance, not an ongoing bypass.
    if sess.expires_at is not None and sess.expires_at < utcnow():
        db.delete(sess)
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="session_expired")
    _enforce_csrf(request, sess)
    return sess


def current_auth_context(request: Request, db: Session = Depends(db_dep)) -> AuthContext:
    token_context = _api_token_context(request, db)
    if token_context is not None:
        return token_context
    sess = current_session(request, db)
    user = db.get(models.User, sess.user_id)
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="not_authenticated")
    membership = None
    if sess.active_org_id:
        membership = (
            db.query(models.Membership)
            .filter(models.Membership.org_id == sess.active_org_id, models.Membership.user_id == user.id)
            .first()
        )
    return AuthContext(
        org_id=sess.active_org_id,
        user_id=user.id,
        membership_id=membership.id if membership else None,
        role=membership.role if membership else None,
        scopes=("*",),
    )


def current_user(sess: models.Session_ = Depends(current_session), db: Session = Depends(db_dep)) -> models.User:
    user = db.get(models.User, sess.user_id)
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="not_authenticated")
    return user


def optional_current_user(auth: AuthContext = Depends(current_auth_context), db: Session = Depends(db_dep)) -> models.User | None:
    if auth.user_id is None:
        return None
    return db.get(models.User, auth.user_id)


def current_membership(
    sess: models.Session_ = Depends(current_session),
    user: models.User = Depends(current_user),
    db: Session = Depends(db_dep),
) -> models.Membership:
    org_id = sess.active_org_id
    if not org_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="no_active_org")
    membership = (
        db.query(models.Membership)
        .filter(models.Membership.org_id == org_id, models.Membership.user_id == user.id)
        .first()
    )
    if not membership:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="not_a_member")
    return membership


def current_org(
    auth: AuthContext = Depends(current_auth_context),
    db: Session = Depends(db_dep),
) -> models.Organization:
    if not auth.org_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="no_active_org")
    if not auth.is_api_token and not auth.membership_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="not_a_member")
    org = db.get(models.Organization, auth.org_id)
    if not org:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="org_not_found")
    return org


def require_admin(membership: models.Membership = Depends(current_membership)) -> models.Membership:
    if membership.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="admin_required")
    return membership
