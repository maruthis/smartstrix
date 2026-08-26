"""Shared helper for writing to the organization audit trail."""

from __future__ import annotations

from sqlalchemy.orm import Session

from . import models


def record_audit(
    db: Session,
    org_id: str,
    actor_user_id: str | None,
    action: str,
    target: str,
    extra: dict | None = None,
) -> None:
    db.add(models.AuditLogEntry(org_id=org_id, actor_user_id=actor_user_id, action=action, target=target, extra=extra or {}))
    db.commit()
