from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import models
from ..audit import record_audit as _record_audit
from ..deps import current_org, current_user, db_dep, require_admin
from ..jobs import enqueue_pr_review
from ..providers import get_github_provider
from ..reports import render_pr_review_report_html, render_report_pdf
from ..run_logs import read_scan_log
from ..settings import settings

router = APIRouter(prefix="/api/pr-reviews", tags=["pr-reviews"])

STATUS_TABS = ["all", "awaiting_merge", "needs_attention", "merged_with_open_findings", "passed"]
# A review's report/log/issues are only meaningful once the scan has
# actually finished — "running" has nothing to show yet, and "failed" has
# no findings and no report worth generating (mirrors pentests.py's
# `_load_pentest_and_issues`, which only allows status == "completed").
_DONE_STATUSES = {"awaiting_merge", "needs_attention", "merged_with_open_findings", "passed"}


def _serialize(p: models.PRReview, repo_names: dict[str, str]) -> dict:
    return {
        "id": p.id,
        "repository_id": p.repository_id,
        "repository_full_name": repo_names.get(p.repository_id, ""),
        "pr_number": p.pr_number,
        "title": p.title,
        "author": p.author,
        "status": p.status,
        "findings_count": p.findings_count,
        "target_branch": p.target_branch,
        "resolved_head_sha": p.resolved_head_sha,
        "error": p.error,
        "llm_input_tokens": p.llm_input_tokens or 0,
        "llm_output_tokens": p.llm_output_tokens or 0,
        "llm_total_tokens": p.llm_total_tokens or 0,
        "created_at": p.created_at.isoformat(),
        "updated_at": p.updated_at.isoformat(),
    }


def _serialize_one(p: models.PRReview, db: Session) -> dict:
    repo = db.get(models.Repository, p.repository_id)
    return _serialize(p, {p.repository_id: repo.full_name if repo else ""})


@router.get("")
def list_pr_reviews(
    status_filter: str | None = None,
    repository_id: str | None = None,
    search: str | None = None,
    org: models.Organization = Depends(current_org),
    db: Session = Depends(db_dep),
) -> dict:
    q = db.query(models.PRReview).filter_by(org_id=org.id)
    if repository_id:
        q = q.filter(models.PRReview.repository_id == repository_id)
    if search:
        like = f"%{search}%"
        q = q.filter(models.PRReview.title.ilike(like))
    if status_filter and status_filter != "all":
        q = q.filter(models.PRReview.status == status_filter)
    reviews = q.order_by(models.PRReview.updated_at.desc()).all()

    all_reviews = db.query(models.PRReview).filter_by(org_id=org.id).all()
    counts = {tab: 0 for tab in STATUS_TABS}
    counts["all"] = len(all_reviews)
    for r in all_reviews:
        counts[r.status] = counts.get(r.status, 0) + 1

    # One batched lookup for every repository referenced by these reviews,
    # instead of one query per row (was N+1 — see saas/TASKS.md).
    repo_ids = {r.repository_id for r in reviews if r.repository_id}
    repo_names = {
        repo.id: repo.full_name for repo in db.query(models.Repository).filter(models.Repository.id.in_(repo_ids)).all()
    }

    return {"items": [_serialize(r, repo_names) for r in reviews], "counts": counts}


class NewPRReviewIn(BaseModel):
    repository_id: str
    pr_number: int
    title: str
    author: str = "unknown"
    # The PR/MR's base branch — sent by the frontend's PR picker when it
    # has real provider data; None for a fully manual entry, in which case
    # the scan falls back to the repository's default_branch.
    target_branch: str | None = None


async def _create_and_enqueue_pr_review(
    db: Session,
    org: models.Organization,
    repo: models.Repository,
    pr_number: int,
    title: str,
    author: str,
    target_branch: str | None,
) -> models.PRReview:
    """Creates the PRReview row (status="running") and enqueues the real
    scan on the shared job worker — shared by the manual trigger endpoint
    and the GitHub webhook handler below. Returns immediately; the caller
    does not wait for the scan to finish (it can take minutes, same as a
    pentest — see jobs.py's `_run_pr_review_job`)."""
    review = models.PRReview(
        org_id=org.id,
        repository_id=repo.id,
        pr_number=pr_number,
        title=title,
        author=author,
        target_branch=target_branch,
    )
    db.add(review)
    db.commit()
    db.refresh(review)
    await enqueue_pr_review(review.id)
    return review


@router.post("")
async def trigger_pr_review(
    body: NewPRReviewIn,
    org: models.Organization = Depends(current_org),
    user: models.User = Depends(current_user),
    db: Session = Depends(db_dep),
) -> dict:
    repo = db.get(models.Repository, body.repository_id)
    if not repo or repo.org_id != org.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="repository_not_found")
    if not settings.enable_real_scan:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="real_scan_not_enabled")

    review = await _create_and_enqueue_pr_review(db, org, repo, body.pr_number, body.title, body.author, body.target_branch)
    _record_audit(db, org.id, user.id, "pr_review.triggered", f"{repo.full_name}#{body.pr_number}")
    return _serialize_one(review, db)


# --------------------------------------------------------------------------
# Settings
# --------------------------------------------------------------------------


def _get_or_create_settings(db: Session, org_id: str) -> models.PRReviewSettings:
    settings_row = db.get(models.PRReviewSettings, org_id)
    if not settings_row:
        settings_row = models.PRReviewSettings(org_id=org_id)
        db.add(settings_row)
        db.commit()
        db.refresh(settings_row)
    return settings_row


def _serialize_settings(s: models.PRReviewSettings) -> dict:
    return {
        "rereview_on_push": s.rereview_on_push,
        "target_branches": s.target_branches,
        "approve_clean_prs": s.approve_clean_prs,
        "block_prs_on_findings": s.block_prs_on_findings,
        "blocking_severities": s.blocking_severities,
        "exclude_bot_accounts": s.exclude_bot_accounts,
        "excluded_usernames": s.excluded_usernames,
        "allow_overage_reviews": s.allow_overage_reviews,
        "review_cap_per_dev": s.review_cap_per_dev,
        "review_cap_period": s.review_cap_period,
    }


@router.get("/settings")
def get_settings(org: models.Organization = Depends(current_org), db: Session = Depends(db_dep)) -> dict:
    return _serialize_settings(_get_or_create_settings(db, org.id))


class UpdateSettingsIn(BaseModel):
    rereview_on_push: bool | None = None
    target_branches: list[str] | None = None
    approve_clean_prs: bool | None = None
    block_prs_on_findings: bool | None = None
    blocking_severities: list[str] | None = None
    exclude_bot_accounts: bool | None = None
    excluded_usernames: list[str] | None = None
    allow_overage_reviews: bool | None = None
    review_cap_per_dev: int | None = None
    review_cap_period: str | None = None


@router.patch("/settings")
def update_settings(
    body: UpdateSettingsIn,
    org: models.Organization = Depends(current_org),
    user: models.User = Depends(current_user),
    _admin=Depends(require_admin),
    db: Session = Depends(db_dep),
) -> dict:
    settings_row = _get_or_create_settings(db, org.id)
    changed = body.model_dump(exclude_unset=True)
    for field, value in changed.items():
        setattr(settings_row, field, value)
    db.commit()
    _record_audit(db, org.id, user.id, "pr_review_settings.updated", "PR review settings", changed)
    return _serialize_settings(settings_row)


# --------------------------------------------------------------------------
# Single review: detail, findings, run log, report.
#
# These use a /{review_id} path param, so they must be registered AFTER
# every literal-path route above (e.g. /settings) — FastAPI/Starlette
# matches routes in registration order, and /{review_id} would otherwise
# swallow a request to /settings by matching review_id="settings".
# --------------------------------------------------------------------------


@router.get("/{review_id}")
def get_pr_review(review_id: str, org: models.Organization = Depends(current_org), db: Session = Depends(db_dep)) -> dict:
    review = db.get(models.PRReview, review_id)
    if not review or review.org_id != org.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="not_found")
    return _serialize_one(review, db)


@router.get("/{review_id}/issues")
def get_pr_review_issues(review_id: str, org: models.Organization = Depends(current_org), db: Session = Depends(db_dep)) -> list[dict]:
    from .issues import _serialize as serialize_issue

    review = db.get(models.PRReview, review_id)
    if not review or review.org_id != org.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="not_found")
    issues = db.query(models.Issue).filter_by(pr_review_id=review_id).all()
    return [serialize_issue(i) for i in issues]


@router.get("/{review_id}/logs")
def get_pr_review_logs(
    review_id: str,
    level: str | None = None,
    agent_id: str | None = None,
    q: str | None = None,
    org: models.Organization = Depends(current_org),
    db: Session = Depends(db_dep),
) -> dict:
    review = db.get(models.PRReview, review_id)
    if not review or review.org_id != org.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="not_found")
    return read_scan_log(review_id, level=level, agent_id=agent_id, q=q)


def _load_pr_review_and_issues(
    review_id: str, org: models.Organization, db: Session
) -> tuple[models.PRReview, models.Repository, list[models.Issue]]:
    review = db.get(models.PRReview, review_id)
    if not review or review.org_id != org.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="not_found")
    if review.status not in _DONE_STATUSES:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="report_not_ready")
    repo = db.get(models.Repository, review.repository_id)
    if repo is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="repository_not_found")
    issues = db.query(models.Issue).filter_by(pr_review_id=review_id).all()
    return review, repo, issues


@router.get("/{review_id}/report", response_class=HTMLResponse)
def view_pr_review_report(review_id: str, org: models.Organization = Depends(current_org), db: Session = Depends(db_dep)) -> HTMLResponse:
    review, repo, issues = _load_pr_review_and_issues(review_id, org, db)
    html = render_pr_review_report_html(review, repo, issues, org)
    return HTMLResponse(content=html)


@router.get("/{review_id}/report/download")
def download_pr_review_report(review_id: str, org: models.Organization = Depends(current_org), db: Session = Depends(db_dep)) -> Response:
    review, repo, issues = _load_pr_review_and_issues(review_id, org, db)
    html = render_pr_review_report_html(review, repo, issues, org)
    pdf_bytes = render_report_pdf(html)
    filename = f"pr-review-report-{review.id}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# --------------------------------------------------------------------------
# GitHub webhook (PR events, @strix mentions)
# --------------------------------------------------------------------------

webhook_router = APIRouter(prefix="/api/webhooks", tags=["pr-reviews"])


@webhook_router.post("/github")
async def github_webhook(request: Request, db: Session = Depends(db_dep)) -> dict:
    payload = await request.body()
    provider = get_github_provider()
    signature = request.headers.get("X-Hub-Signature-256")
    if not provider.verify_webhook_signature(payload=payload, signature_header=signature):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="invalid_signature")

    event = request.headers.get("X-GitHub-Event", "")
    try:
        data = json.loads(payload or b"{}")
    except json.JSONDecodeError:
        return {"ok": True, "skipped": "invalid_json"}

    full_name = (data.get("repository") or {}).get("full_name")
    pr_number: int | None = None
    title = ""
    author = ""
    base_branch: str | None = None

    if event == "pull_request" and data.get("action") in ("opened", "reopened", "synchronize"):
        pr = data.get("pull_request") or {}
        pr_number = pr.get("number")
        title = pr.get("title", "")
        author = (pr.get("user") or {}).get("login", "unknown")
        base_branch = (pr.get("base") or {}).get("ref")
        is_push_update = data.get("action") == "synchronize"
    elif event == "issue_comment" and data.get("action") == "created" and "pull_request" in (data.get("issue") or {}):
        comment_body = (data.get("comment") or {}).get("body", "")
        if "@strix" not in comment_body.lower():
            return {"ok": True, "skipped": "no_strix_mention"}
        issue = data.get("issue") or {}
        pr_number = issue.get("number")
        title = issue.get("title", "")
        author = (issue.get("user") or {}).get("login", "unknown")
        is_push_update = False
    else:
        return {"ok": True, "skipped": f"unhandled_event:{event}/{data.get('action')}"}

    if not full_name or pr_number is None:
        return {"ok": True, "skipped": "missing_repository_or_pr_number"}

    repo = db.query(models.Repository).filter_by(full_name=full_name).first()
    if not repo:
        return {"ok": True, "skipped": "repository_not_registered"}
    if not repo.auto_review_enabled and event == "pull_request":
        return {"ok": True, "skipped": "auto_review_disabled"}

    org = db.get(models.Organization, repo.org_id)
    if not org:
        return {"ok": True, "skipped": "org_not_found"}

    settings_row = _get_or_create_settings(db, org.id)
    if is_push_update and not settings_row.rereview_on_push:
        return {"ok": True, "skipped": "rereview_on_push_disabled"}
    if settings_row.target_branches and base_branch and base_branch not in settings_row.target_branches:
        return {"ok": True, "skipped": "branch_not_targeted"}
    if settings_row.exclude_bot_accounts and author.endswith("[bot]"):
        return {"ok": True, "skipped": "excluded_bot_account"}
    if author in settings_row.excluded_usernames:
        return {"ok": True, "skipped": "excluded_username"}

    if not settings.enable_real_scan:
        return {"ok": True, "skipped": "real_scan_not_enabled"}

    review = await _create_and_enqueue_pr_review(db, org, repo, pr_number, title, author, base_branch)
    return {"ok": True, "review_id": review.id, "status": review.status}
