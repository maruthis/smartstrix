"""Thin wrapper around croniter for PentestSchedule's next-run computation.

Kept as its own tiny module (no app-internal imports) so both
`routers/pentests.py` (create/re-enable a schedule) and `scheduler.py`
(the periodic checker) can import it without a circular import — the
scheduler already needs to call into `routers/pentests.py` to reuse the
same pentest-creation path a manual "Run pentest" click uses.
"""

from __future__ import annotations

import logging
from datetime import datetime

from croniter import croniter

logger = logging.getLogger("saas.cron")


def compute_next_run(cron_expr: str, base: datetime) -> datetime | None:
    """Next run time strictly after `base`, or None if `cron_expr` is invalid.

    A standard 5-field cron expression (minute hour day month weekday).
    `base`'s tzinfo (naive-UTC everywhere in this backend — see
    time_utils.py) is preserved on the returned value.
    """
    try:
        return croniter(cron_expr, base).get_next(datetime)
    except (ValueError, KeyError):
        logger.warning("invalid cron_expr %r on a pentest schedule; leaving unscheduled", cron_expr)
        return None
