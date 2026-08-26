from __future__ import annotations

import hashlib
import hmac
import json
import logging
from typing import Any
from urllib.parse import urlparse

import httpx
from fastapi import HTTPException

from . import models
from .db import SessionLocal
from .public_hosts import assert_public_https_url, hostname_resolves_public

logger = logging.getLogger("saas.webhooks")


def _matches(events: list | None, event: str) -> bool:
    configured = {str(item) for item in events or []}
    return "*" in configured or event in configured


def _signature(secret: str, body: bytes) -> str:
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def deliver_event(org_id: str, event: str, payload: dict[str, Any]) -> None:
    """Best-effort synchronous delivery used from the async job worker via
    ``asyncio.to_thread``. It owns its DB session so network I/O cannot leak
    or reuse the scan transaction's session across threads."""
    db = SessionLocal()
    try:
        webhooks = (
            db.query(models.Webhook)
            .filter(models.Webhook.org_id == org_id, models.Webhook.status.in_(["active", "failing"]))
            .all()
        )
        body = json.dumps({"event": event, "payload": payload}, separators=(",", ":"), sort_keys=True).encode("utf-8")
        with httpx.Client(timeout=5.0) as client:
            for webhook in webhooks:
                if not _matches(webhook.events, event):
                    continue
                try:
                    assert_public_https_url(webhook.url)
                    host = urlparse(webhook.url).hostname
                    if not host or not hostname_resolves_public(host):
                        raise ValueError("webhook host is not a public address")
                    response = client.post(
                        webhook.url,
                        content=body,
                        headers={
                            "content-type": "application/json",
                            "x-strix-event": event,
                            "x-strix-signature": _signature(webhook.secret, body),
                        },
                    )
                    webhook.status = "active" if 200 <= response.status_code < 300 else "failing"
                except (httpx.HTTPError, HTTPException, ValueError):
                    logger.exception("webhook delivery failed: org=%s webhook=%s event=%s", org_id, webhook.id, event)
                    webhook.status = "failing"
        db.commit()
    finally:
        db.close()
