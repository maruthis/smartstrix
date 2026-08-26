from app import models, seed
from app.db import SessionLocal


def test_seed_creates_demo_org_user_and_repo():
    seed.seed()

    db = SessionLocal()
    try:
        org = db.query(models.Organization).filter_by(name=seed.DEMO_ORG_NAME).first()
        assert org is not None
        user = db.query(models.User).filter_by(email=seed.DEMO_USER_EMAIL).first()
        assert user is not None
        assert db.query(models.Membership).filter_by(org_id=org.id, user_id=user.id).first() is not None
        assert db.query(models.Repository).filter_by(org_id=org.id, full_name=seed.DEMO_REPO).first() is not None
        assert db.get(models.Subscription, org.id) is not None
        assert db.get(models.PRReviewSettings, org.id) is not None
    finally:
        db.close()


def test_seed_is_idempotent(capsys):
    seed.seed()
    seed.seed()  # second call should detect the existing org and skip

    captured = capsys.readouterr()
    assert "already present" in captured.out

    db = SessionLocal()
    try:
        count = db.query(models.Organization).filter_by(name=seed.DEMO_ORG_NAME).count()
        assert count == 1
    finally:
        db.close()


def test_seed_reuses_existing_user_without_an_org():
    db = SessionLocal()
    try:
        db.add(models.User(email=seed.DEMO_USER_EMAIL, name="Pre-existing"))
        db.commit()
    finally:
        db.close()

    seed.seed()

    db = SessionLocal()
    try:
        users = db.query(models.User).filter_by(email=seed.DEMO_USER_EMAIL).all()
        assert len(users) == 1
        assert users[0].name == "Pre-existing"
    finally:
        db.close()
