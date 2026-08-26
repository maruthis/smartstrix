"""Tests for app.cron.compute_next_run — the thin croniter wrapper used by
both the schedule-creation endpoint and app.scheduler's periodic checker."""

from __future__ import annotations

from datetime import datetime

from app.cron import compute_next_run


def test_computes_the_next_weekly_sunday_midnight_occurrence():
    # 2026-08-21 is a Friday.
    base = datetime(2026, 8, 21, 12, 0, 0)
    next_run = compute_next_run("0 0 * * 0", base)
    assert next_run == datetime(2026, 8, 23, 0, 0, 0)


def test_computes_the_next_daily_occurrence():
    base = datetime(2026, 8, 21, 12, 30, 0)
    next_run = compute_next_run("0 0 * * *", base)
    assert next_run == datetime(2026, 8, 22, 0, 0, 0)


def test_result_is_always_strictly_after_base():
    base = datetime(2026, 8, 23, 0, 0, 0)  # exactly a scheduled occurrence
    next_run = compute_next_run("0 0 * * 0", base)
    assert next_run is not None
    assert next_run > base


def test_returns_none_for_an_invalid_cron_expression():
    assert compute_next_run("not a cron expression", datetime(2026, 8, 21)) is None


def test_returns_none_for_a_malformed_field_count():
    assert compute_next_run("0 0 * *", datetime(2026, 8, 21)) is None
