from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import models
from ..audit import record_audit as _record_audit
from ..deps import current_org, current_user, db_dep

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


def _serialize(k: models.KnowledgeEntry) -> dict:
    return {
        "id": k.id,
        "type": k.type,
        "description": k.description,
        "scope_type": k.scope_type,
        "scope_id": k.scope_id,
        "created_at": k.created_at.isoformat(),
    }


@router.get("")
def list_knowledge(
    search: str | None = None,
    scope_type: str | None = None,
    org: models.Organization = Depends(current_org),
    db: Session = Depends(db_dep),
) -> list[dict]:
    q = db.query(models.KnowledgeEntry).filter_by(org_id=org.id)
    if scope_type and scope_type != "all":
        q = q.filter(models.KnowledgeEntry.scope_type == scope_type)
    if search:
        q = q.filter(models.KnowledgeEntry.description.ilike(f"%{search}%"))
    entries = q.order_by(models.KnowledgeEntry.created_at.desc()).all()
    return [_serialize(e) for e in entries]


class NewKnowledgeIn(BaseModel):
    type: str = "business_logic"
    description: str
    scope_type: str = "global"
    scope_id: str | None = None


@router.post("")
def add_knowledge(
    body: NewKnowledgeIn,
    org: models.Organization = Depends(current_org),
    user: models.User = Depends(current_user),
    db: Session = Depends(db_dep),
) -> dict:
    if not body.description.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="description_required")
    if body.scope_type not in {"global", "repository", "domain"}:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="invalid_scope_type")
    scope_id = body.scope_id.strip() if body.scope_id else None
    if body.scope_type == "global":
        scope_id = None
    elif not scope_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="scope_id_required")
    entry = models.KnowledgeEntry(
        org_id=org.id,
        type=body.type,
        description=body.description.strip(),
        scope_type=body.scope_type,
        scope_id=scope_id,
    )
    db.add(entry)
    db.commit()
    _record_audit(db, org.id, user.id, "knowledge.added", entry.description[:80])
    return _serialize(entry)


@router.delete("/{entry_id}")
def delete_knowledge(
    entry_id: str,
    org: models.Organization = Depends(current_org),
    user: models.User = Depends(current_user),
    db: Session = Depends(db_dep),
) -> dict:
    entry = db.get(models.KnowledgeEntry, entry_id)
    if not entry or entry.org_id != org.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="not_found")
    description = entry.description[:80]
    db.delete(entry)
    db.commit()
    _record_audit(db, org.id, user.id, "knowledge.deleted", description)
    return {"ok": True}


def relevant_entries(db: Session, org_id: str, *, repository_id: str | None = None, domain_id: str | None = None) -> list[models.KnowledgeEntry]:
    """Knowledge entries that should be injected into agent context for a
    given scan/chat target: global entries plus ones scoped to this exact
    repository/domain. Currently only used by the chat router's mock reply
    — jobs.py's real-scan path does not call this yet (see TASKS.md P8-4;
    that's a known, tracked gap, not an oversight)."""
    q = db.query(models.KnowledgeEntry).filter_by(org_id=org_id)
    entries = q.all()
    return [
        e
        for e in entries
        if e.scope_type == "global"
        or (e.scope_type == "repository" and e.scope_id == repository_id)
        or (e.scope_type == "domain" and e.scope_id == domain_id)
    ]
