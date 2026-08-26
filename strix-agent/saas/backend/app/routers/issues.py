from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models
from ..deps import current_org, current_user, db_dep
from ..audit import record_audit as _record_audit

router = APIRouter(prefix="/api/issues", tags=["issues"])

VALID_STATUSES = {"open", "in_progress", "snoozed", "fixed", "ignored"}


def _serialize(i: models.Issue) -> dict:
    return {
        "id": i.id,
        "org_id": i.org_id,
        "pentest_id": i.pentest_id,
        "pr_review_id": i.pr_review_id,
        "repository_id": i.repository_id,
        "domain_id": i.domain_id,
        "title": i.title,
        "description": i.description,
        "severity": i.severity,
        "status": i.status,
        "cvss": i.cvss,
        "cvss_breakdown": i.cvss_breakdown,
        "technical_analysis": i.technical_analysis,
        "remediation_steps": i.remediation_steps,
        "poc_description": i.poc_description,
        "poc_script_code": i.poc_script_code,
        "code_before": i.code_before,
        "code_after": i.code_after,
        "target": i.target,
        "endpoint": i.endpoint,
        "fix_effort": i.fix_effort,
        "source": i.source,
        "created_at": i.created_at.isoformat(),
        "updated_at": i.updated_at.isoformat(),
    }


@router.get("")
def list_issues(
    status_filter: str | None = None,
    severity: str | None = None,
    repository_id: str | None = None,
    domain_id: str | None = None,
    pentest_id: str | None = None,
    org: models.Organization = Depends(current_org),
    db: Session = Depends(db_dep),
) -> dict:
    q = db.query(models.Issue).filter_by(org_id=org.id)
    if status_filter:
        q = q.filter(models.Issue.status == status_filter)
    if severity:
        q = q.filter(models.Issue.severity == severity)
    if repository_id:
        q = q.filter(models.Issue.repository_id == repository_id)
    if domain_id:
        q = q.filter(models.Issue.domain_id == domain_id)
    if pentest_id:
        q = q.filter(models.Issue.pentest_id == pentest_id)
    issues = q.order_by(models.Issue.created_at.desc()).all()

    # Grouped SQL aggregates instead of pulling every org issue's full row
    # into Python twice more just to tally severities/statuses (was 3x full
    # scans — see saas/TASKS.md). Scoped by the same repository/domain/pentest
    # filters as the list above (but not status_filter — severity_counts
    # already excludes fixed/ignored on its own, and status_counts is what
    # drives the status tabs, so it must cover every status regardless of
    # which one is currently selected) so the summary strip and tab counts
    # stay consistent with whatever repo/pentest is selected instead of
    # always showing org-wide totals.
    def _scoped(query):
        if repository_id:
            query = query.filter(models.Issue.repository_id == repository_id)
        if domain_id:
            query = query.filter(models.Issue.domain_id == domain_id)
        if pentest_id:
            query = query.filter(models.Issue.pentest_id == pentest_id)
        return query

    severity_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    severity_rows = (
        _scoped(db.query(models.Issue.severity, func.count(models.Issue.id)))
        .filter(models.Issue.org_id == org.id, models.Issue.status.notin_(["fixed", "ignored"]))
        .group_by(models.Issue.severity)
        .all()
    )
    for sev, count in severity_rows:
        severity_counts[sev] = count

    status_counts = {s: 0 for s in ["all", "open", "in_progress", "snoozed", "fixed", "ignored"]}
    status_rows = (
        _scoped(db.query(models.Issue.status, func.count(models.Issue.id)))
        .filter(models.Issue.org_id == org.id)
        .group_by(models.Issue.status)
        .all()
    )
    for st, count in status_rows:
        status_counts[st] = count
        status_counts["all"] += count

    return {
        "items": [_serialize(i) for i in issues],
        "severity_counts": severity_counts,
        "status_counts": status_counts,
    }


@router.get("/{issue_id}")
def get_issue(issue_id: str, org: models.Organization = Depends(current_org), db: Session = Depends(db_dep)) -> dict:
    issue = db.get(models.Issue, issue_id)
    if not issue or issue.org_id != org.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="not_found")
    return _serialize(issue)


class UpdateIssueStatusIn(BaseModel):
    status: str


@router.patch("/{issue_id}/status")
def update_issue_status(
    issue_id: str,
    body: UpdateIssueStatusIn,
    org: models.Organization = Depends(current_org),
    user: models.User = Depends(current_user),
    db: Session = Depends(db_dep),
) -> dict:
    if body.status not in VALID_STATUSES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="invalid_status")
    issue = db.get(models.Issue, issue_id)
    if not issue or issue.org_id != org.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="not_found")
    issue.status = body.status
    db.commit()
    _record_audit(db, org.id, user.id, "issue.status_updated", issue.title, {"status": body.status})
    return _serialize(issue)
