"""Compact coverage / agent-graph summary for the SaaS pentest UI."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:
    from pathlib import Path


logger = logging.getLogger("saas.coverage")

MOCK_COVERAGE: dict[str, Any] = {
    "mode": "mock",
    "finish_scan": False,
    "complete": False,
    "scan_status": "mock",
    "exit_reason": None,
    "caveats": [
        "This run used the demo scanner. Findings are canned samples, not evidence for the target."
    ],
    "summary": {},
    "gaps": [],
    "agents": [],
}


def summarize_coverage_document(
    document: dict[str, Any],
    *,
    finish_scan: bool | None = None,
) -> dict[str, Any]:
    completeness = (
        document.get("completeness") if isinstance(document.get("completeness"), dict) else {}
    )
    observed = (
        document.get("machine_observed")
        if isinstance(document.get("machine_observed"), dict)
        else {}
    )
    agents = observed.get("agents") if isinstance(observed.get("agents"), list) else []
    gaps = document.get("gaps") if isinstance(document.get("gaps"), list) else []
    summary = document.get("summary") if isinstance(document.get("summary"), dict) else {}
    complete = bool(completeness.get("complete"))
    scan_status = completeness.get("scan_status")
    if finish_scan is None:
        finish_scan = complete and scan_status == "completed"
    return {
        "mode": "real",
        "finish_scan": bool(finish_scan),
        "complete": complete,
        "scan_status": scan_status,
        "exit_reason": completeness.get("exit_reason"),
        "caveats": [str(item) for item in (completeness.get("caveats") or []) if item],
        "summary": {
            "surfaces_reviewed": summary.get("surfaces_reviewed", 0),
            "findings_filed": summary.get("findings_filed", 0),
            "gaps": summary.get("gaps", len(gaps)),
            "outcomes": summary.get("outcomes") or {},
        },
        "gaps": [_compact_gap(gap) for gap in gaps[:40] if isinstance(gap, dict)],
        "agents": [_compact_agent(agent) for agent in agents if isinstance(agent, dict)],
        **(
            {"recall": document["recall"]}
            if isinstance(document.get("recall"), dict)
            else {}
        ),
    }


def read_coverage_summary(
    run_dir: Path,
    *,
    finish_scan: bool | None = None,
) -> dict[str, Any] | None:
    path = run_dir / "coverage.json"
    if not path.exists():
        return None
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        logger.exception("could not read coverage.json at %s", path)
        return None
    if not isinstance(document, dict):
        return None
    return summarize_coverage_document(document, finish_scan=finish_scan)


def empty_real_coverage(*, finish_scan: bool) -> dict[str, Any]:
    return {
        "mode": "real",
        "finish_scan": finish_scan,
        "complete": finish_scan,
        "scan_status": "completed" if finish_scan else "failed",
        "exit_reason": None if finish_scan else "finish_scan_missing",
        "caveats": []
        if finish_scan
        else ["coverage.json was not written. Do not treat this run as a complete assessment."],
        "summary": {},
        "gaps": [],
        "agents": [],
    }


def _compact_gap(gap: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": gap.get("kind") or "",
        "surface": gap.get("surface") or "",
        "risk_area": gap.get("risk_area") or "",
        "detail": gap.get("detail") or "",
    }


def _compact_agent(agent: dict[str, Any]) -> dict[str, Any]:
    skills = agent.get("skills") if isinstance(agent.get("skills"), list) else []
    return {
        "agent_id": agent.get("agent_id") or "",
        "agent_name": agent.get("agent_name") or "",
        "status": agent.get("status") or "",
        "skills": [str(skill) for skill in skills],
        "is_root": bool(agent.get("is_root")),
    }
