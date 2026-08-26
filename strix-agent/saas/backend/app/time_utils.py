"""Naive-UTC timestamp helper.

SQLite's DateTime columns don't round-trip tzinfo (values come back naive
even when stored with `timezone=True`), so mixing aware and naive
datetimes across a request/response cycle raises `TypeError` on comparison.
Standardizing on naive-but-always-UTC datetimes everywhere in this backend
avoids that; switching to Postgres later doesn't require touching this.
"""

from __future__ import annotations

from datetime import datetime, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)
