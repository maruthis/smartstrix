"""Covers the "create on first access" branches for rows that org-creation
normally seeds eagerly (Subscription, PRReviewSettings) — reachable if that
row is ever missing, e.g. for orgs created before those seed statements
existed, or deleted out-of-band."""

from app import models
from app.db import SessionLocal


def test_billing_recreates_missing_subscription_row(auth_client):
    client, org = auth_client

    db = SessionLocal()
    try:
        db.delete(db.get(models.Subscription, org["id"]))
        db.commit()
    finally:
        db.close()

    res = client.get("/api/settings/billing")
    assert res.status_code == 200
    assert res.json()["status"] == "trialing"

    db = SessionLocal()
    try:
        assert db.get(models.Subscription, org["id"]) is not None
    finally:
        db.close()


def test_pr_review_settings_recreates_missing_row(auth_client):
    client, org = auth_client

    db = SessionLocal()
    try:
        db.delete(db.get(models.PRReviewSettings, org["id"]))
        db.commit()
    finally:
        db.close()

    res = client.get("/api/pr-reviews/settings")
    assert res.status_code == 200
    assert res.json()["block_prs_on_findings"] is True

    db = SessionLocal()
    try:
        assert db.get(models.PRReviewSettings, org["id"]) is not None
    finally:
        db.close()
