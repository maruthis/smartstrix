"""Recall vs known defects and diffs between successive runs."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from strix.known_defects import findings_from_issues, list_checklists, score_findings

from . import models
from .secret_text import redact_secret_shaped_text


if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def score_pentest_recall(
    pentest: models.Pentest,
    issues: list[models.Issue],
    *,
    checklist_id: str = "gitlab_mcp_vapt",
) -> dict[str, Any]:
    return score_findings(
        findings_from_issues(issues),
        checklist_id=checklist_id,
        skills=list(pentest.skills or []),
    )


def available_checklists() -> list[dict[str, Any]]:
    return list_checklists()


def _issue_key(issue: models.Issue) -> tuple[str, str]:
    return ((issue.file_path or "").lower(), (issue.title or "").strip().lower())


def _issue_brief(issue: models.Issue) -> dict[str, Any]:
    return {
        "id": issue.id,
        "title": issue.title,
        "severity": issue.severity,
        "source": issue.source,
        "file_path": issue.file_path,
        "line_number": issue.line_number,
        "disposition": issue.disposition or "pending",
    }


def compare_pentest_runs(
    db: Session,
    pentest: models.Pentest,
    current_issues: list[models.Issue],
) -> dict[str, Any]:
    previous = (
        db.query(models.Pentest)
        .filter(
            models.Pentest.org_id == pentest.org_id,
            models.Pentest.target_type == pentest.target_type,
            models.Pentest.target_id == pentest.target_id,
            models.Pentest.id != pentest.id,
            models.Pentest.status.in_(("completed", "failed")),
            models.Pentest.created_at < pentest.created_at,
        )
        .order_by(models.Pentest.created_at.desc())
        .first()
    )
    if previous is None:
        return {
            "previous_pentest_id": None,
            "still_open": [],
            "new": [_issue_brief(issue) for issue in current_issues],
            "gone": [],
        }
    previous_issues = db.query(models.Issue).filter_by(pentest_id=previous.id).all()
    current_by_key = {_issue_key(issue): issue for issue in current_issues}
    previous_by_key = {_issue_key(issue): issue for issue in previous_issues}
    still_open = [
        _issue_brief(issue)
        for key, issue in current_by_key.items()
        if key in previous_by_key
    ]
    new = [
        _issue_brief(issue)
        for key, issue in current_by_key.items()
        if key not in previous_by_key
    ]
    gone = [
        _issue_brief(issue)
        for key, issue in previous_by_key.items()
        if key not in current_by_key
    ]
    return {
        "previous_pentest_id": previous.id,
        "previous_status": previous.status,
        "previous_finished_at": previous.finished_at.isoformat() if previous.finished_at else None,
        "still_open": still_open,
        "new": new,
        "gone": gone,
    }


def retest_instructions(issue: models.Issue) -> str:
    location = issue.file_path or issue.target or issue.endpoint or "not provided"
    if issue.file_path and issue.line_number:
        location = f"{issue.file_path}:{issue.line_number}"
    notes = redact_secret_shaped_text(issue.description or issue.technical_analysis or "")
    return (
        "Retest this previously reported finding. Confirm whether it still exists. "
        "Do not treat the prior run as coverage.\n"
        f"Title: {issue.title}\n"
        f"Severity: {issue.severity}\n"
        f"Location: {location}\n"
        f"Notes: {notes[:800]}"
    )
