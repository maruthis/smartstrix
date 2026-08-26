"""Tests for app.scheduler — the periodic checker that fires due
PentestSchedule rows (see saas/backend/app/scheduler.py). Talks to the DB
directly (mirrors test_jobs.py's style) rather than through the API, since
scheduler ticks aren't triggered by any request."""

from __future__ import annotations

from datetime import timedelta

from app import jobs, models, scheduler
from app.db import SessionLocal
from app.time_utils import utcnow


def _make_org_and_repo(db, name: str = "ScheduleCo"):
    org = models.Organization(name=name)
    db.add(org)
    db.flush()
    repo = models.Repository(org_id=org.id, full_name=f"{name.lower()}/widgets")
    db.add(repo)
    db.commit()
    return org, repo


def _make_schedule(
    db,
    org,
    repo,
    *,
    enabled: bool = True,
    next_run_at=None,
    cron_expr: str = "0 0 * * 0",
):
    schedule = models.PentestSchedule(
        org_id=org.id,
        target_type="repository",
        target_id=repo.id,
        cron_expr=cron_expr,
        enabled=enabled,
        next_run_at=next_run_at,
    )
    db.add(schedule)
    db.commit()
    db.refresh(schedule)
    return schedule


async def test_run_due_schedules_fires_an_overdue_schedule():
    db = SessionLocal()
    try:
        org, repo = _make_org_and_repo(db)
        schedule = _make_schedule(db, org, repo, next_run_at=utcnow() - timedelta(minutes=1))
        schedule_id, org_id = schedule.id, org.id
    finally:
        db.close()

    # enqueue_pentest() requires the job queue to be running — normally
    # started by the FastAPI lifespan; these tests talk to the DB/scheduler
    # directly (no TestClient), so start/stop it explicitly, matching
    # test_jobs.py's own pattern for the same reason.
    await jobs.start_worker()
    try:
        fired = await scheduler.run_due_schedules()
    finally:
        await jobs.stop_worker()
    assert fired == 1

    db = SessionLocal()
    try:
        refreshed = db.get(models.PentestSchedule, schedule_id)
        assert refreshed.last_run_at is not None
        assert refreshed.next_run_at is not None
        assert refreshed.next_run_at > utcnow()  # advanced to the next occurrence

        pentests = db.query(models.Pentest).filter_by(org_id=org_id).all()
        assert len(pentests) == 1
        assert pentests[0].status != "failed"  # successfully created + enqueued
        assert pentests[0].created_by is None  # no acting user for a scheduled run

        audit = (
            db.query(models.AuditLogEntry)
            .filter_by(org_id=org_id, action="pentest_schedule.fired")
            .one_or_none()
        )
        assert audit is not None
    finally:
        db.close()


async def test_run_due_schedules_skips_a_not_yet_due_schedule():
    db = SessionLocal()
    try:
        org, repo = _make_org_and_repo(db)
        _make_schedule(db, org, repo, next_run_at=utcnow() + timedelta(days=1))
        org_id = org.id
    finally:
        db.close()

    fired = await scheduler.run_due_schedules()
    assert fired == 0

    db = SessionLocal()
    try:
        assert db.query(models.Pentest).filter_by(org_id=org_id).count() == 0
    finally:
        db.close()


async def test_run_due_schedules_skips_a_disabled_schedule_even_if_overdue():
    db = SessionLocal()
    try:
        org, repo = _make_org_and_repo(db)
        _make_schedule(db, org, repo, enabled=False, next_run_at=utcnow() - timedelta(days=1))
        org_id = org.id
    finally:
        db.close()

    fired = await scheduler.run_due_schedules()
    assert fired == 0

    db = SessionLocal()
    try:
        assert db.query(models.Pentest).filter_by(org_id=org_id).count() == 0
    finally:
        db.close()


async def test_run_due_schedules_backfills_a_missing_next_run_at_without_firing():
    """A schedule that predates next_run_at being computed at creation time
    (or created by a future admin-tools direct-insert) gets it filled in on
    the next tick, but that tick itself doesn't count as a fire."""
    db = SessionLocal()
    try:
        org, repo = _make_org_and_repo(db)
        schedule = _make_schedule(db, org, repo, next_run_at=None)
        schedule_id = schedule.id
    finally:
        db.close()

    fired = await scheduler.run_due_schedules()
    assert fired == 0

    db = SessionLocal()
    try:
        refreshed = db.get(models.PentestSchedule, schedule_id)
        assert refreshed.next_run_at is not None
        assert db.query(models.Pentest).count() == 0
    finally:
        db.close()


async def test_run_due_schedules_disables_an_orphaned_schedule():
    """The schedule's org was deleted out from under it. `fired` counts a
    due-and-attempted tick, not a successfully-created pentest — see the
    "target is gone" test below for the same distinction."""
    db = SessionLocal()
    try:
        org, repo = _make_org_and_repo(db)
        schedule = _make_schedule(db, org, repo, next_run_at=utcnow() - timedelta(minutes=1))
        schedule_id = schedule.id
        db.delete(org)
        db.commit()
    finally:
        db.close()

    fired = await scheduler.run_due_schedules()
    assert fired == 1

    db = SessionLocal()
    try:
        refreshed = db.get(models.PentestSchedule, schedule_id)
        assert refreshed.enabled is False
        assert db.query(models.Pentest).count() == 0
    finally:
        db.close()


async def test_run_due_schedules_still_advances_next_run_at_when_the_target_is_gone():
    """The repository was deleted after the schedule was created —
    create_and_enqueue_pentest raises a 404 HTTPException, which must not
    wedge the schedule into being "due" on every subsequent tick forever."""
    db = SessionLocal()
    try:
        org, repo = _make_org_and_repo(db)
        schedule = _make_schedule(db, org, repo, next_run_at=utcnow() - timedelta(minutes=1))
        schedule_id = schedule.id
        db.delete(repo)
        db.commit()
    finally:
        db.close()

    fired = await scheduler.run_due_schedules()
    assert fired == 1  # attempted, even though enqueueing itself failed

    db = SessionLocal()
    try:
        refreshed = db.get(models.PentestSchedule, schedule_id)
        assert refreshed.last_run_at is not None
        assert refreshed.next_run_at is not None
        assert db.query(models.Pentest).count() == 0
    finally:
        db.close()


async def test_start_and_stop_are_idempotent():
    assert scheduler._task is None
    await scheduler.start()
    first_task = scheduler._task
    assert first_task is not None
    await scheduler.start()  # second call is a no-op, not a second task
    assert scheduler._task is first_task
    await scheduler.stop()
    assert scheduler._task is None
    await scheduler.stop()  # second call is also a no-op
