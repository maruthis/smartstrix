import time

from fastapi.testclient import TestClient

from app import models
from app.db import SessionLocal
from app.main import app


def test_reconciles_pentests_orphaned_by_a_previous_process_on_startup():
    # A Pentest left at status="running" when the app starts can only mean
    # the previous process was killed mid-scan (a clean in-process failure
    # already sets "failed" — see jobs.py). Seed one directly, bypassing the
    # API entirely, so it exists *before* the lifespan below runs.
    db = SessionLocal()
    try:
        org = models.Organization(name="Acme")
        db.add(org)
        db.flush()
        user = models.User(email="orphan-owner@example.com", name="Owner")
        db.add(user)
        db.flush()
        pentest = models.Pentest(
            org_id=org.id,
            target_type="repository",
            target_id="r1",
            target_label="acme/widgets",
            scan_mode="deep",
            status="running",
            created_by=user.id,
        )
        db.add(pentest)
        db.commit()
        pentest_id, org_id = pentest.id, org.id
    finally:
        db.close()

    with TestClient(app) as client:
        assert client.get("/api/health").status_code == 200

    db = SessionLocal()
    try:
        refreshed = db.get(models.Pentest, pentest_id)
        assert refreshed.status == "failed"
        assert refreshed.finished_at is not None

        entry = (
            db.query(models.AuditLogEntry)
            .filter_by(org_id=org_id, action="pentest.interrupted")
            .first()
        )
        assert entry is not None
        assert entry.extra["reason"] == "backend restarted mid-scan"
    finally:
        db.close()


def test_startup_is_a_noop_when_nothing_is_orphaned():
    with TestClient(app) as client:
        assert client.get("/api/health").status_code == 200


def test_requeues_pentests_still_queued_from_a_previous_process_on_startup():
    # A Pentest at status="queued" was enqueued into the previous process's
    # now-gone in-memory asyncio.Queue (jobs.py) and never even started —
    # unlike a "running" row, nothing about it needs discarding, so it
    # should simply run once the new process's worker comes up.
    db = SessionLocal()
    try:
        org = models.Organization(name="Acme")
        db.add(org)
        db.flush()
        pentest = models.Pentest(
            org_id=org.id,
            target_type="repository",
            target_id="r1",
            target_label="acme/widgets",
            scan_mode="deep",
            status="queued",
        )
        db.add(pentest)
        db.commit()
        pentest_id, org_id = pentest.id, org.id
    finally:
        db.close()

    with TestClient(app) as client:
        assert client.get("/api/health").status_code == 200

        db = SessionLocal()
        try:
            for _ in range(50):
                db.expire_all()
                refreshed = db.get(models.Pentest, pentest_id)
                if refreshed.status == "completed":
                    break
                time.sleep(0.05)
            assert refreshed.status == "completed"

            entry = db.query(models.AuditLogEntry).filter_by(org_id=org_id, action="pentest.requeued").first()
            assert entry is not None
        finally:
            db.close()


def test_reconciles_pr_reviews_orphaned_by_a_previous_process_on_startup():
    # PRReview has no separate "queued" state (see models.PRReview) — the
    # row is created at status="running" before the worker ever dequeues
    # it, so this same status has to cover both "never started" and
    # "started, then killed" — both are marked failed rather than
    # auto-resumed (see main.py's reconciliation docstring for why).
    db = SessionLocal()
    try:
        org = models.Organization(name="Acme")
        db.add(org)
        db.flush()
        repo = models.Repository(org_id=org.id, full_name="acme/widgets")
        db.add(repo)
        db.flush()
        review = models.PRReview(org_id=org.id, repository_id=repo.id, pr_number=42, status="running")
        db.add(review)
        db.commit()
        review_id, org_id = review.id, org.id
    finally:
        db.close()

    with TestClient(app) as client:
        assert client.get("/api/health").status_code == 200

    db = SessionLocal()
    try:
        refreshed = db.get(models.PRReview, review_id)
        assert refreshed.status == "failed"
        assert refreshed.error == "interrupted"

        entry = db.query(models.AuditLogEntry).filter_by(org_id=org_id, action="pr_review.interrupted").first()
        assert entry is not None
        assert entry.extra["reason"] == "backend restarted mid-review"
    finally:
        db.close()
