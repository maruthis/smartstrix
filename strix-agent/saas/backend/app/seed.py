"""Idempotent local dev seed: one demo org/user/repo matching the product screenshots.

Run with: uv run python -m app.seed
"""

from __future__ import annotations

from datetime import timedelta

from . import models
from .db import SessionLocal, init_db
from .time_utils import utcnow

DEMO_USER_EMAIL = "iammaruv@gmail.com"
DEMO_USER_NAME = "Maru"
DEMO_ORG_NAME = "MaruVAPT"
DEMO_REPO = "maruthis/anything-llm"


def seed() -> None:
    init_db()
    db = SessionLocal()
    try:
        org = db.query(models.Organization).filter_by(name=DEMO_ORG_NAME).first()
        if org:
            print(f"Seed already present: org {org.id!r} ({DEMO_ORG_NAME}). Nothing to do.")
            return

        user = db.query(models.User).filter_by(email=DEMO_USER_EMAIL).first()
        if not user:
            user = models.User(email=DEMO_USER_EMAIL, name=DEMO_USER_NAME)
            db.add(user)
            db.flush()

        org = models.Organization(name=DEMO_ORG_NAME)
        db.add(org)
        db.flush()

        db.add(models.Membership(org_id=org.id, user_id=user.id, role="admin"))
        db.add(
            models.Subscription(
                org_id=org.id,
                plan="pro_trial",
                status="trialing",
                trial_ends_at=utcnow() + timedelta(days=7),
                card_added=False,
            )
        )
        db.add(models.PRReviewSettings(org_id=org.id))
        db.add(
            models.Repository(
                org_id=org.id,
                provider="github",
                full_name=DEMO_REPO,
                default_branch="main",
                auto_review_enabled=True,
            )
        )
        db.add(models.Integration(org_id=org.id, provider="github", account_label="maruthis"))
        db.commit()
        print(f"Seeded org {org.id!r} ({DEMO_ORG_NAME}) with user {user.email} and repo {DEMO_REPO}.")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
