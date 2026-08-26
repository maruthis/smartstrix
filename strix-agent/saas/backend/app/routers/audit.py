from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import models
from ..deps import current_org, db_dep, require_admin

router = APIRouter(prefix="/api/settings/audit-logs", tags=["settings"])
request_log_router = APIRouter(prefix="/api/settings/request-logs", tags=["settings"])

PAGE_SIZE_DEFAULT = 50
PAGE_SIZE_MAX = 200


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


# Both logs are admin-only: they expose who-did-what across the whole org
# (including other members' actions and every API call any member made),
# which is exactly the kind of thing require_admin already gates elsewhere
# (see tokens.py, repositories.py deletion) — a plain member viewing it
# previously was an oversight, not a deliberate choice.


@router.get("")
def list_audit_logs(
    page: int = 1,
    page_size: int = PAGE_SIZE_DEFAULT,
    actor_user_id: str | None = None,
    action: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    org: models.Organization = Depends(current_org),
    _admin=Depends(require_admin),
    db: Session = Depends(db_dep),
) -> dict:
    page_size = max(1, min(page_size, PAGE_SIZE_MAX))
    page = max(1, page)

    q = db.query(models.AuditLogEntry).filter_by(org_id=org.id)
    if actor_user_id:
        q = q.filter(models.AuditLogEntry.actor_user_id == actor_user_id)
    if action:
        q = q.filter(models.AuditLogEntry.action.ilike(f"%{action}%"))
    from_dt, to_dt = _parse_date(date_from), _parse_date(date_to)
    if from_dt:
        q = q.filter(models.AuditLogEntry.created_at >= from_dt)
    if to_dt:
        q = q.filter(models.AuditLogEntry.created_at <= to_dt)

    total = q.count()
    entries = q.order_by(models.AuditLogEntry.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()

    actor_ids = {e.actor_user_id for e in entries if e.actor_user_id}
    actors = {u.id: u.email for u in db.query(models.User).filter(models.User.id.in_(actor_ids)).all()} if actor_ids else {}

    items = [
        {
            "id": e.id,
            "actor_user_id": e.actor_user_id,
            "actor_email": actors.get(e.actor_user_id, "system"),
            "action": e.action,
            "target": e.target,
            "extra": e.extra,
            "created_at": e.created_at.isoformat(),
        }
        for e in entries
    ]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@request_log_router.get("")
def list_request_logs(
    page: int = 1,
    page_size: int = PAGE_SIZE_DEFAULT,
    method: str | None = None,
    min_status: int | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    org: models.Organization = Depends(current_org),
    _admin=Depends(require_admin),
    db: Session = Depends(db_dep),
) -> dict:
    page_size = max(1, min(page_size, PAGE_SIZE_MAX))
    page = max(1, page)

    q = db.query(models.RequestLogEntry).filter_by(org_id=org.id)
    if method:
        q = q.filter(models.RequestLogEntry.method == method.upper())
    if min_status:
        q = q.filter(models.RequestLogEntry.status_code >= min_status)
    from_dt, to_dt = _parse_date(date_from), _parse_date(date_to)
    if from_dt:
        q = q.filter(models.RequestLogEntry.created_at >= from_dt)
    if to_dt:
        q = q.filter(models.RequestLogEntry.created_at <= to_dt)

    total = q.count()
    entries = q.order_by(models.RequestLogEntry.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()

    actor_ids = {e.actor_user_id for e in entries if e.actor_user_id}
    actors = {u.id: u.email for u in db.query(models.User).filter(models.User.id.in_(actor_ids)).all()} if actor_ids else {}

    items = [
        {
            "id": e.id,
            "actor_email": actors.get(e.actor_user_id, "system"),
            "method": e.method,
            "path": e.path,
            "status_code": e.status_code,
            "duration_ms": e.duration_ms,
            "created_at": e.created_at.isoformat(),
        }
        for e in entries
    ]
    return {"items": items, "total": total, "page": page, "page_size": page_size}
