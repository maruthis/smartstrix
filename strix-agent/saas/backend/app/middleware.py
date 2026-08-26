"""Best-effort HTTP activity logging.

Only mutating requests (non-GET) and error responses (status >= 400) are
recorded, per RequestLogEntry's docstring — a routine GET, which several
pages poll every few seconds, would otherwise flood the table.
"""

from __future__ import annotations

import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from . import models
from .db import SessionLocal
from .settings import settings

logger = logging.getLogger("saas.requests")


class RequestLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        start = time.monotonic()
        response = await call_next(request)
        duration_ms = int((time.monotonic() - start) * 1000)

        if request.method != "GET" or response.status_code >= 400:
            self._record(request, response.status_code, duration_ms)

        return response

    def _record(self, request: Request, status_code: int, duration_ms: int) -> None:
        # Never let logging break or slow down the actual request — this
        # runs after the response is already computed, so a failure here
        # must not surface to the caller.
        try:
            org_id, actor_user_id = self._resolve_actor(request)
            db = SessionLocal()
            try:
                db.add(
                    models.RequestLogEntry(
                        org_id=org_id,
                        actor_user_id=actor_user_id,
                        method=request.method,
                        path=request.url.path,
                        status_code=status_code,
                        duration_ms=duration_ms,
                    )
                )
                db.commit()
            finally:
                db.close()
        except Exception:  # noqa: BLE001 - logging must never break a request
            logger.exception("failed to write request log entry")

    def _resolve_actor(self, request: Request) -> tuple[str | None, str | None]:
        token = request.cookies.get(settings.session_cookie_name)
        if not token:
            return None, None
        db = SessionLocal()
        try:
            sess = db.get(models.Session_, token)
            if not sess:
                return None, None
            return sess.active_org_id, sess.user_id
        finally:
            db.close()
