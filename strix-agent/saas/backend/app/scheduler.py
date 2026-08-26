"""Periodic checker that fires due PentestSchedule rows.

Mirrors jobs.py's own pattern deliberately: no cron daemon/APScheduler
process, just a single asyncio background task (started from the FastAPI
lifespan — see main.py) that wakes up once a minute, finds every enabled
schedule whose `next_run_at` has passed, and enqueues a pentest for it via
the exact same `create_and_enqueue_pentest` path a manual "Run pentest"
click uses — so a scheduled run gets identical treatment (mock-vs-real
scan selection, per-org LLM settings, audit trail wiring) with no
real-vs-scheduled branch anywhere else in the pipeline.
"""

from __future__ import annotations

import asyncio
import logging

from . import models
from .audit import record_audit
from .cron import compute_next_run
from .db import SessionLocal
from .routers.pentests import create_and_enqueue_pentest
from .time_utils import utcnow


logger = logging.getLogger("saas.scheduler")

_CHECK_INTERVAL_SECONDS = 60

_task: asyncio.Task | None = None


async def start() -> None:
    global _task  # noqa: PLW0603
    if _task is None:
        _task = asyncio.create_task(_loop())


async def stop() -> None:
    global _task  # noqa: PLW0603
    if _task is not None:
        _task.cancel()
        _task = None


async def _loop() -> None:
    while True:
        try:
            await run_due_schedules()
        except Exception:  # noqa: BLE001 - a broken tick must not kill the scheduler
            logger.exception("scheduler tick failed")
        await asyncio.sleep(_CHECK_INTERVAL_SECONDS)


async def run_due_schedules() -> int:
    """One tick. Returns the number of schedules fired — mainly for tests."""
    db = SessionLocal()
    try:
        now = utcnow()
        fired = 0
        for schedule in db.query(models.PentestSchedule).filter_by(enabled=True).all():
            if schedule.next_run_at is None:
                # First tick after creation shouldn't normally hit this —
                # the create-schedule endpoint sets next_run_at up front —
                # but backfills it here too, defensively, without firing.
                schedule.next_run_at = compute_next_run(schedule.cron_expr, now)
                db.commit()
                continue
            if schedule.next_run_at <= now:
                await _fire(db, schedule, now)
                fired += 1
        return fired
    finally:
        db.close()


async def _fire(db, schedule: models.PentestSchedule, now) -> None:  # noqa: ANN001
    org = db.get(models.Organization, schedule.org_id)
    if org is None:
        # Orphaned schedule (its org was deleted) — disable it so it stops
        # being reconsidered every tick.
        schedule.enabled = False
        db.commit()
        return
    try:
        pentest = await create_and_enqueue_pentest(
            db,
            org,
            None,  # no acting user for a scheduler-triggered run
            schedule.target_type,
            schedule.target_id,
            schedule.scan_mode,
            skills=schedule.skills,
        )
        record_audit(db, org.id, None, "pentest_schedule.fired", schedule.target_id, {"pentest_id": pentest.id})
    except Exception:  # noqa: BLE001 - e.g. target deleted since the schedule was made
        logger.exception("scheduled pentest for schedule %s failed to enqueue", schedule.id)
    finally:
        schedule.last_run_at = now
        schedule.next_run_at = compute_next_run(schedule.cron_expr, now)
        db.commit()
