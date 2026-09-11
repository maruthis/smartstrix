"""Score a scan against a known-defect checklist.

An independent VAPT is the quality loop for this assistant: recall against
defects a human already found, not a go-live gate. Misses tell us which
baseline greps and skills to deepen next.

Lives outside ``strix.scan`` so the SaaS API can import it without pulling
the scan/playbook/coverage stack (and the optional ``agents`` SDK).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ChecklistItem:
    item_id: str
    title: str
    severity: str
    tokens: tuple[str, ...]
    baseline_titles: tuple[str, ...] = ()


@dataclass(frozen=True)
class KnownFindingChecklist:
    checklist_id: str
    title: str
    source: str
    items: tuple[ChecklistItem, ...]


GITLAB_MCP_VAPT = KnownFindingChecklist(
    checklist_id="gitlab_mcp_vapt",
    title="GitLab MCP VAPT (Sep 2026)",
    source=(
        "Independent VAPT of awgment-gitlab-mcpserver-dev v2.1.0. "
        "10 known defects. Used to score assistant recall, not as residual-risk closure."
    ),
    items=(
        ChecklistItem(
            item_id="V1",
            title="Unauthenticated HTTP MCP endpoint with no endpoint auth or TLS",
            severity="critical",
            tokens=(
                "binds on all interfaces",
                "0.0.0.0",
                "unauthenticated http mcp",
                "no endpoint auth",
                "mcp http transport has no endpoint authentication",
            ),
            baseline_titles=(
                "Service binds on all interfaces (0.0.0.0 / ::)",
                "MCP HTTP transport has no endpoint authentication",
            ),
        ),
        ChecklistItem(
            item_id="V2",
            title="Destructive MCP tools lack human-in-the-loop / approval gates",
            severity="high",
            tokens=(
                "human-in-the-loop",
                "require_approval",
                "destructive mcp tool",
                "approval gate",
            ),
            baseline_titles=("Destructive MCP tools have no approval gate",),
        ),
        ChecklistItem(
            item_id="V3",
            title="Raw HTTP headers (with caller credentials) logged at WARNING level",
            severity="high",
            tokens=("headers logged at runtime", "raw headers received"),
            baseline_titles=("HTTP request headers logged at runtime",),
        ),
        ChecklistItem(
            item_id="V4",
            title="TCP transport framing missing max_message_size (unbounded allocation)",
            severity="medium",
            tokens=("readexactly", "max_message_size", "unbounded tcp"),
            baseline_titles=("Unbounded TCP readexactly without a max size",),
        ),
        ChecklistItem(
            item_id="V5",
            title="Stdio transport lacks application-layer authentication",
            severity="medium",
            tokens=(
                "stdio transport lacks",
                "application-layer authentication",
                "stdio mode has no client identity",
            ),
        ),
        ChecklistItem(
            item_id="V6",
            title="Unbounded resource consumption / no rate limiting",
            severity="medium",
            tokens=("no rate limiting", "unbounded resource", "mcp http handler has no rate limiting"),
            baseline_titles=("MCP HTTP handler has no rate limiting",),
        ),
        ChecklistItem(
            item_id="V7",
            title="Dynamic URL path segments not URL-encoded",
            severity="medium",
            tokens=("url-encoded", "path segments not url-encoded", "quote("),
            baseline_titles=("URL path segment interpolated without encoding",),
        ),
        ChecklistItem(
            item_id="V8",
            title="Generic exception strings returned to MCP clients",
            severity="low",
            tokens=("exception strings returned", "str(exc)", "str(e)"),
            baseline_titles=("Exception text returned to MCP/API clients",),
        ),
        ChecklistItem(
            item_id="V9",
            title="Tool execution audit hook defined but not wired into the registry",
            severity="low",
            tokens=("audit_tool_execution", "audit hook"),
            baseline_titles=("audit_tool_execution is defined but never called",),
        ),
        ChecklistItem(
            item_id="V10",
            title="Verbose validation errors disclose framework version and internal model names",
            severity="low",
            tokens=("verbose validation", "pydantic validation error"),
        ),
    ),
)

CHECKLISTS: dict[str, KnownFindingChecklist] = {
    GITLAB_MCP_VAPT.checklist_id: GITLAB_MCP_VAPT,
}

_MCP_APPLICABILITY_TOKENS = ("mcp", "model context protocol", "0.0.0.0", "tools/call")


def list_checklists() -> list[dict[str, Any]]:
    return [
        {
            "id": item.checklist_id,
            "title": item.title,
            "source": item.source,
            "item_count": len(item.items),
        }
        for item in CHECKLISTS.values()
    ]


def _haystack(finding: Mapping[str, Any]) -> str:
    parts = [
        finding.get("title"),
        finding.get("description"),
        finding.get("technical_analysis"),
        finding.get("target"),
        finding.get("endpoint"),
        finding.get("file_path"),
        finding.get("poc_description"),
        finding.get("evidence"),
    ]
    return " ".join(str(part).lower() for part in parts if part)


def _item_hits(item: ChecklistItem, findings: Sequence[Mapping[str, Any]]) -> list[str]:
    matched: list[str] = []
    for finding in findings:
        title = str(finding.get("title") or "")
        lowered_title = title.lower()
        if any(baseline.lower() in lowered_title for baseline in item.baseline_titles):
            matched.append(title or item.item_id)
            continue
        haystack = _haystack(finding)
        if any(token.lower() in haystack for token in item.tokens):
            matched.append(title or item.item_id)
    return matched


def score_findings(
    findings: Sequence[Mapping[str, Any]],
    *,
    checklist_id: str = "gitlab_mcp_vapt",
    skills: Sequence[str] | None = None,
) -> dict[str, Any]:
    checklist = CHECKLISTS.get(checklist_id)
    if checklist is None:
        return {
            "applicable": False,
            "checklist_id": checklist_id,
            "error": "unknown_checklist",
        }
    applicable = _checklist_applicable(checklist, findings, skills or [])
    items = []
    hit_count = 0
    for item in checklist.items:
        matched_titles = _item_hits(item, findings)
        hit = bool(matched_titles)
        if hit:
            hit_count += 1
        items.append(
            {
                "id": item.item_id,
                "title": item.title,
                "severity": item.severity,
                "status": "hit" if hit else "miss",
                "matched_finding_titles": matched_titles[:8],
            }
        )
    total = len(checklist.items)
    missed = total - hit_count
    return {
        "applicable": applicable,
        "checklist_id": checklist.checklist_id,
        "title": checklist.title,
        "source": checklist.source,
        "matched": hit_count,
        "missed": missed,
        "total": total,
        "recall": (hit_count / total) if total else 0.0,
        "items": items,
    }


def _checklist_applicable(
    checklist: KnownFindingChecklist,
    findings: Sequence[Mapping[str, Any]],
    skills: Sequence[str],
) -> bool:
    if checklist.checklist_id != "gitlab_mcp_vapt":
        return True
    if any("mcp" in str(skill).lower() for skill in skills):
        return True
    joined = " ".join(_haystack(finding) for finding in findings)
    return any(token in joined for token in _MCP_APPLICABILITY_TOKENS)


def findings_from_issues(issues: Sequence[Any]) -> list[dict[str, Any]]:
    """Adapt SaaS Issue rows or similar objects into scorer mappings."""
    out: list[dict[str, Any]] = []
    for issue in issues:
        if isinstance(issue, Mapping):
            out.append(dict(issue))
            continue
        out.append(
            {
                "title": getattr(issue, "title", "") or "",
                "description": getattr(issue, "description", "") or "",
                "technical_analysis": getattr(issue, "technical_analysis", "") or "",
                "target": getattr(issue, "target", "") or "",
                "endpoint": getattr(issue, "endpoint", "") or "",
                "file_path": getattr(issue, "file_path", None),
                "poc_description": getattr(issue, "poc_description", "") or "",
            }
        )
    return out
