from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import models
from ..audit import record_audit as _record_audit
from ..deps import current_org, current_user, db_dep
from ..settings import settings

router = APIRouter(prefix="/api/chat", tags=["chat"])

CATEGORIES = ["web", "code", "cloud", "recon", "network", "threat_intel", "compliance"]

SUGGESTIONS: dict[str, list[dict]] = {
    "web": [
        {"title": "Test API authorization", "prompt": "Check my API endpoints for broken access control and privilege escalation issues."},
        {"title": "Analyze OAuth flows", "prompt": "Evaluate the token handling and redirect validation in my OAuth setup."},
        {"title": "Detect SSRF vectors", "prompt": "Find server-side request forgery paths that could reach internal services."},
        {"title": "Audit business logic", "prompt": "Look for logic flaws in my app - race conditions, state manipulation, bypasses."},
    ],
    "code": [
        {"title": "Review authentication code", "prompt": "Review my authentication implementation for common vulnerabilities."},
        {"title": "Find injection flaws", "prompt": "Search the codebase for SQL/command/template injection sinks."},
        {"title": "Check secrets handling", "prompt": "Look for hardcoded secrets or unsafe secret storage in the codebase."},
        {"title": "Review dependency risk", "prompt": "Flag outdated or vulnerable dependencies in the project manifest."},
    ],
    "cloud": [
        {"title": "Audit IAM policies", "prompt": "Review IAM roles/policies for overly permissive access."},
        {"title": "Check storage exposure", "prompt": "Look for publicly exposed storage buckets or misconfigured ACLs."},
        {"title": "Review network exposure", "prompt": "Check security groups/firewalls for overly broad ingress rules."},
        {"title": "Audit secrets management", "prompt": "Review how cloud secrets/credentials are stored and rotated."},
    ],
    "recon": [
        {"title": "Map external attack surface", "prompt": "Enumerate subdomains, exposed services, and endpoints for my domain."},
        {"title": "Fingerprint tech stack", "prompt": "Identify frameworks, CMS, and versions in use across my assets."},
    ],
    "network": [
        {"title": "Scan open ports", "prompt": "Identify open ports and exposed services on my network target."},
        {"title": "Review segmentation", "prompt": "Assess network segmentation between environments."},
    ],
    "threat_intel": [
        {"title": "Check breach exposure", "prompt": "Check if my domain/org has appeared in known breach data."},
    ],
    "compliance": [
        {"title": "Map findings to SOC 2", "prompt": "Map current open findings to relevant SOC 2 control gaps."},
    ],
}


@router.get("/suggestions")
def get_suggestions() -> dict:
    return {"categories": CATEGORIES, "suggestions": SUGGESTIONS}


def _serialize_session(s: models.ChatSession) -> dict:
    return {"id": s.id, "title": s.title, "category": s.category, "created_at": s.created_at.isoformat()}


def _serialize_message(m: models.ChatMessage) -> dict:
    return {"id": m.id, "role": m.role, "content": m.content, "created_at": m.created_at.isoformat()}


@router.get("/sessions")
def list_sessions(
    org: models.Organization = Depends(current_org),
    user: models.User = Depends(current_user),
    db: Session = Depends(db_dep),
) -> list[dict]:
    sessions = (
        db.query(models.ChatSession)
        .filter_by(org_id=org.id, user_id=user.id)
        .order_by(models.ChatSession.created_at.desc())
        .all()
    )
    return [_serialize_session(s) for s in sessions]


class NewSessionIn(BaseModel):
    category: str = "web"


@router.post("/sessions")
def create_session(
    body: NewSessionIn,
    org: models.Organization = Depends(current_org),
    user: models.User = Depends(current_user),
    db: Session = Depends(db_dep),
) -> dict:
    session = models.ChatSession(org_id=org.id, user_id=user.id, category=body.category)
    db.add(session)
    db.commit()
    _record_audit(db, org.id, user.id, "chat.session_created", session.category)
    return _serialize_session(session)


def _owned_session(
    session_id: str,
    org: models.Organization,
    user: models.User,
    db: Session,
) -> models.ChatSession:
    session = db.get(models.ChatSession, session_id)
    if not session or session.org_id != org.id or session.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="not_found")
    return session


@router.get("/sessions/{session_id}/messages")
def list_messages(
    session_id: str,
    org: models.Organization = Depends(current_org),
    user: models.User = Depends(current_user),
    db: Session = Depends(db_dep),
) -> list[dict]:
    session = _owned_session(session_id, org, user, db)
    return [_serialize_message(m) for m in session.messages]


class NewMessageIn(BaseModel):
    content: str
    repository_ids: list[str] = []


@router.post("/sessions/{session_id}/messages")
async def send_message(
    session_id: str,
    body: NewMessageIn,
    org: models.Organization = Depends(current_org),
    user: models.User = Depends(current_user),
    db: Session = Depends(db_dep),
) -> list[dict]:
    session = _owned_session(session_id, org, user, db)
    if not body.content.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="content_required")

    user_msg = models.ChatMessage(session_id=session.id, role="user", content=body.content.strip())
    db.add(user_msg)

    from .knowledge import relevant_entries

    context_entries = relevant_entries(db, org.id, repository_id=body.repository_ids[0] if body.repository_ids else None)
    reply = await _run_chat_turn(db, org, user, body, context_entries)
    assistant_msg = models.ChatMessage(session_id=session.id, role="assistant", content=reply)
    db.add(assistant_msg)

    if session.title == "New chat":
        session.title = body.content.strip()[:60]

    db.commit()
    return [_serialize_message(user_msg), _serialize_message(assistant_msg)]


async def _run_chat_turn(
    db: Session,
    org: models.Organization,
    user: models.User,
    body: NewMessageIn,
    context_entries: list[models.KnowledgeEntry],
) -> str:
    """Real reply, never a fabricated one. With no repository attached
    there's nothing to scan, so say that plainly rather than pretending a
    review started. With one or more repositories attached and real
    scanning enabled, this actually triggers a pentest per repository —
    the exact same `create_and_enqueue_pentest` path "New Pentest" uses,
    just with the chat message threaded through as the scan's custom
    instruction (`Pentest.custom_instructions` -> scan_config's
    `user_instructions`, which strix's `build_root_task` folds into the
    root task). The reply reports what was actually started, never a
    fabricated "found N issues" — a real scan takes minutes, so results
    show up on the Pentests/Issues pages once it finishes, not in this
    turn."""
    if not body.repository_ids:
        return (
            'I can\'t scan anything without a target. Click "Add repositories" below to attach '
            "one or more connected repositories, then send your request again."
        )

    if not settings.enable_real_scan:
        return (
            "Real scanning isn't enabled for this deployment (SAAS_ENABLE_REAL_SCAN), so I can't "
            "run an actual scan here. Ask an admin to enable it, or use New Pentest once it's on."
        )

    from .pentests import create_and_enqueue_pentest

    repos = []
    for repo_id in body.repository_ids:
        repo = db.get(models.Repository, repo_id)
        if repo and repo.org_id == org.id:
            repos.append(repo)

    if not repos:
        return "I couldn't find those repositories in this organization — try attaching them again."

    started: list[tuple[str, str]] = []
    for repo in repos:
        pentest = await create_and_enqueue_pentest(
            db, org, user, "repository", repo.id, scan_mode="quick", custom_instructions=body.content.strip()
        )
        started.append((repo.full_name, pentest.id))

    context_note = (
        f" I'm also factoring in {len(context_entries)} piece(s) of knowledge base context." if context_entries else ""
    )
    scan_list = "; ".join(f"{name} (pentest {pid[:8]})" for name, pid in started)
    return (
        f"Started a real scan for: {scan_list}.{context_note} This runs in the background — track progress "
        "and results on the Pentests page once it's done."
    )
