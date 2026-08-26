"""Shared reader for a strix engine run's on-disk log file.

Both a Pentest and a PR review are one `run_strix_scan` run each — the
engine writes `strix.log` to `run_dir_for(<scan_id>)` the same way in both
cases (a PR review passes its own `review.id` as `scan_id`/`run_name`, see
jobs.py's `_run_real_pr_review_scan`) — so the parsing/filtering logic only
needs to live once.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any


_LOG_LINE_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3}) (?P<level>\S+)\s+"
    r"(?P<scan_id>\S+) (?P<agent_id>\S+) (?P<logger>[^:]+): (?P<message>.*)$"
)
_MAX_LOG_LINES = 5000


def read_scan_log(
    scan_id: str,
    *,
    level: str | None = None,
    agent_id: str | None = None,
    q: str | None = None,
) -> dict:
    from strix.core.paths import run_record_path

    run_dir = _find_run_dir(scan_id)
    log_path = run_dir / "strix.log"
    usage = _read_llm_usage(run_record_path(run_dir))
    if not log_path.exists():
        return {"available": False, "lines": [], "total_lines": 0, "total_matched": 0, "agent_ids": [], "llm_usage": usage}

    level_filter = level.upper() if level else None
    query = q.lower() if q else None

    parsed: list[dict] = []
    agent_ids: set[str] = set()
    total_lines = 0
    with log_path.open("r", encoding="utf-8", errors="replace") as fh:
        for raw_line in fh:
            raw_line = raw_line.rstrip("\n")
            if not raw_line:
                continue
            total_lines += 1
            m = _LOG_LINE_RE.match(raw_line)
            if not m:
                # Continuation of a multi-line message (e.g. a traceback) —
                # append to the previous entry's message rather than dropping it.
                if parsed:
                    parsed[-1]["message"] += "\n" + raw_line
                continue
            entry = m.groupdict()
            if entry["agent_id"] != "-":
                agent_ids.add(entry["agent_id"])
            parsed.append(entry)

    matched = parsed
    if level_filter:
        matched = [e for e in matched if e["level"] == level_filter]
    if agent_id:
        matched = [e for e in matched if e["agent_id"] == agent_id]
    if query:
        matched = [e for e in matched if query in e["message"].lower()]

    total_matched = len(matched)
    tail = matched[-_MAX_LOG_LINES:]

    return {
        "available": True,
        "lines": tail,
        "total_lines": total_lines,
        "total_matched": total_matched,
        "agent_ids": sorted(agent_ids),
        "llm_usage": usage,
    }


def _find_run_dir(scan_id: str) -> Path:
    from strix.core.paths import RUNS_DIR_NAME, run_dir_for

    backend_root = Path(__file__).resolve().parents[1]
    repo_root = backend_root.parents[1]
    workspace_root = repo_root.parent
    candidates = [
        run_dir_for(scan_id),
        # The SaaS backend is commonly started from either the repository
        # root or saas/backend. Engine runs are written relative to the
        # process cwd, so the API log reader must tolerate both roots.
        backend_root / RUNS_DIR_NAME / scan_id,
        repo_root / RUNS_DIR_NAME / scan_id,
    ]
    # Local development often has multiple Strix checkouts under the same
    # workspace (e.g. strix, strix-agent). If the worker was started from a
    # sibling checkout but the API route is served from this one, still find
    # the durable run artifact by scan id.
    for sibling_backend in workspace_root.glob("*/saas/backend"):
        candidates.append(sibling_backend / RUNS_DIR_NAME / scan_id)
    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        if (resolved / "strix.log").exists() or (resolved / "run.json").exists():
            return resolved
    return candidates[0]


def _read_llm_usage(run_record: Any) -> dict:
    if not run_record.exists():
        return {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    try:
        import json

        data = json.loads(run_record.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - logs are best-effort diagnostic data
        return {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    raw = data.get("llm_usage") if isinstance(data, dict) else None
    if not isinstance(raw, dict):
        return {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    input_tokens = _int_or_zero(raw.get("input_tokens"))
    output_tokens = _int_or_zero(raw.get("output_tokens"))
    total_tokens = _int_or_zero(raw.get("total_tokens")) or input_tokens + output_tokens
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
    }


def _int_or_zero(value: object) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0
