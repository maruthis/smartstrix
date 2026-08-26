from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import jobs, models, scheduler
from .audit import record_audit
from .db import SessionLocal, init_db
from .middleware import RequestLogMiddleware
from .routers import ALL_ROUTERS
from .settings import settings
from .time_utils import utcnow


async def _reconcile_interrupted_jobs() -> None:
    """Recover from the job queue being purely in-process memory (see
    jobs.py's module docstring): a crash or restart drops whatever was
    queued or running, and a Pentest/PRReview row doesn't know that on its
    own — it just sits at whatever status it had, forever, with nothing
    left to finish it. Called after `jobs.start_worker()` so the
    re-enqueue below has a queue to land in.

    - Pentest status='running': a clean in-process failure already sets
      'failed' (see jobs.py), so 'running' at startup can only mean the
      process itself was killed mid-scan. Nothing about the attempt is
      recoverable (a partial clone/scan dir may be inconsistent), so this
      marks it failed rather than re-running it silently.
    - Pentest status='queued': never even started — enqueued in the
      previous process's now-gone in-memory queue. Nothing was attempted,
      so this is safe to simply re-enqueue rather than fail.
    - PRReview status='running': reviews have no separate 'queued' state
      (see models.PRReview) — the row is created at 'running' before the
      worker ever dequeues it, so this same status covers "never started"
      and "started, then killed" alike. Both are marked failed rather than
      auto-resumed: unlike a fresh Pentest re-enqueue, a review may have a
      partial PR clone/checkout on disk, and re-triggering a check run
      against a PR automatically (rather than on the user's request) is a
      more visible, more surprising action to take without asking.
    """
    db = SessionLocal()
    try:
        running_pentests = db.query(models.Pentest).filter(models.Pentest.status == "running").all()
        for pentest in running_pentests:
            pentest.status = "failed"
            pentest.finished_at = utcnow()
            db.commit()
            record_audit(
                db,
                pentest.org_id,
                pentest.created_by,
                "pentest.interrupted",
                pentest.target_label,
                {"reason": "backend restarted mid-scan"},
            )

        queued_pentests = db.query(models.Pentest).filter(models.Pentest.status == "queued").all()
        for pentest in queued_pentests:
            record_audit(
                db,
                pentest.org_id,
                pentest.created_by,
                "pentest.requeued",
                pentest.target_label,
                {"reason": "backend restarted before this pentest started"},
            )
            await jobs.enqueue_pentest(pentest.id)

        running_reviews = db.query(models.PRReview).filter(models.PRReview.status == "running").all()
        for review in running_reviews:
            review.status = "failed"
            review.error = "interrupted"
            db.commit()
            record_audit(
                db,
                review.org_id,
                None,
                "pr_review.interrupted",
                str(review.pr_number),
                {"reason": "backend restarted mid-review"},
            )
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    await jobs.start_worker()
    await _reconcile_interrupted_jobs()
    await scheduler.start()
    yield
    await scheduler.stop()
    await jobs.stop_worker()


app = FastAPI(title="Strix SaaS API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestLogMiddleware)

for router in ALL_ROUTERS:
    app.include_router(router)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}
