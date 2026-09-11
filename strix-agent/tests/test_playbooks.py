"""Machine playbook gates: required specialists, review mode, reported-without-vuln."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from strix.scan.playbooks import (
    MCP_LIVE_PLAYBOOK,
    attach_required_playbooks,
    classify_review_mode,
    extra_checklist_keys,
    matching_required_playbook,
    playbook_to_dict,
    required_playbooks_for,
    validate_mcp_not_closed_by_live_401,
    validate_playbook_finish,
    validate_reported_coverage_has_findings,
    validate_required_playbook_agents,
)
from strix.tools.coverage.tools import (
    _record_impl,
    get_coverage_entries,
    hydrate_coverage_from_disk,
)
from strix.tools.finish.tool import REQUIRED_COVERAGE_CATEGORIES, _do_finish


if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture(autouse=True)
def _empty_ledger(tmp_path: Path) -> None:
    hydrate_coverage_from_disk(tmp_path)


def _graph(*children: dict[str, object]) -> dict[str, object]:
    statuses = {"root": "completed"}
    names = {"root": "Root Agent"}
    metadata: dict[str, object] = {"root": {"skills": [], "task": "orchestrate"}}
    parent_of: dict[str, str | None] = {"root": None}
    for index, child in enumerate(children, start=1):
        agent_id = str(child.get("agent_id") or f"child-{index}")
        statuses[agent_id] = "completed"
        names[agent_id] = str(child.get("name") or agent_id)
        metadata[agent_id] = {
            "skills": list(child.get("skills") or []),
            "task": child.get("task") or "",
            "review_mode": child.get("review_mode") or "",
        }
        parent_of[agent_id] = "root"
    return {
        "statuses": statuses,
        "names": names,
        "metadata": metadata,
        "parent_of": parent_of,
    }


def test_mcp_source_plus_live_url_requires_whitebox_and_live_playbooks() -> None:
    playbooks = required_playbooks_for(
        {"mcp", "llm", "agentic"}, has_source=True, has_live_url=True
    )
    skills_modes = {(pb.skills, pb.review_mode) for pb in playbooks}
    assert (("mcp_server",), "whitebox") in skills_modes
    assert (("mcp_server",), "live") in skills_modes
    assert (("llm_prompt_injection",), "whitebox") in skills_modes
    assert (("llm_applications",), "whitebox") in skills_modes
    assert (("ai_ml_governance",), "whitebox") in skills_modes
    assert (("agentic_system_security",), "whitebox") in skills_modes
    assert any(pb.checklist_key == "access_control" for pb in playbooks)
    assert any(pb.checklist_key == "authentication" for pb in playbooks)
    assert any(pb.checklist_key == "injection" for pb in playbooks)


def test_llm_only_tree_does_not_require_mcp() -> None:
    playbooks = required_playbooks_for({"llm"}, has_source=True, has_live_url=False)
    skills = {pb.skills for pb in playbooks}
    assert ("llm_prompt_injection",) in skills
    assert ("mcp_server",) not in skills
    assert MCP_LIVE_PLAYBOOK not in playbooks


def test_url_only_without_source_skips_whitebox_rows() -> None:
    playbooks = required_playbooks_for({"mcp"}, has_source=False, has_live_url=True)
    assert playbooks == [MCP_LIVE_PLAYBOOK]


def test_attach_required_playbooks_persists_mcp_detection(tmp_path: Path) -> None:
    (tmp_path / "server.py").write_text("from mcp.server import Server\n")
    scan_config: dict[str, object] = {
        "targets": [
            {"type": "repository", "details": {"cloned_repo_path": str(tmp_path)}},
            {"type": "web_application", "details": {"target_url": "https://api.example/mcp"}},
        ]
    }
    playbooks = attach_required_playbooks(scan_config, [{"source_path": str(tmp_path)}])
    assert "mcp" in scan_config["detected_surfaces"]
    assert any(pb.checklist_key == "mcp_server" for pb in playbooks)
    assert scan_config["required_playbooks"]


def test_matching_required_playbook_requires_skill_and_mode() -> None:
    playbooks = required_playbooks_for({"mcp"}, has_source=True, has_live_url=True)
    assert (
        matching_required_playbook(
            playbooks, skills=["mcp_server"], review_mode="whitebox", name="MCP WB"
        )
        is not None
    )
    assert (
        matching_required_playbook(
            playbooks, skills=["mcp_server"], review_mode="live", name="MCP Live"
        )
        is not None
    )
    assert (
        matching_required_playbook(
            playbooks, skills=["graphql"], review_mode="whitebox", name="GraphQL"
        )
        is None
    )


def test_live_httpx_agent_does_not_satisfy_whitebox_mcp() -> None:
    playbooks = required_playbooks_for({"mcp"}, has_source=True, has_live_url=False)
    mcp_whitebox = next(pb for pb in playbooks if pb.checklist_key == "mcp_server")
    graph = _graph(
        {
            "name": "Dynamic Test",
            "skills": ["mcp_server", "httpx"],
            "task": "Live CORS and 401 probes against https://api.example/mcp",
        }
    )
    errors = validate_required_playbook_agents([mcp_whitebox], graph, [])
    assert any("whitebox" in error and "mcp_server" in error for error in errors)


def test_declared_whitebox_agent_with_coverage_satisfies_mcp() -> None:
    playbooks = required_playbooks_for({"mcp"}, has_source=True, has_live_url=False)
    mcp_whitebox = next(pb for pb in playbooks if pb.checklist_key == "mcp_server")
    graph = _graph(
        {
            "name": "MCP whitebox",
            "skills": ["mcp_server"],
            "task": "Review app/ handler bind and tool registry",
            "review_mode": "whitebox",
        }
    )
    _record_impl(
        surface="app/server/stateless_handler.py",
        risk_area="MCP server tools/call auth",
        outcome="no_issue_found",
        evidence="Handler requires a session token before call_tool.",
        agent_id="child-1",
        agent_name="MCP whitebox",
    )
    errors = validate_required_playbook_agents([mcp_whitebox], graph, get_coverage_entries())
    assert errors == []


def test_classify_review_mode_prefers_declared_then_hints() -> None:
    assert classify_review_mode({"review_mode": "live", "task": "read the source"}) == "live"
    assert classify_review_mode({"task": "white-box review of app/", "skills": []}) == "whitebox"
    live_agent = {"name": "httpx recon", "task": "CORS on https://x", "skills": ["httpx"]}
    assert classify_review_mode(live_agent) == "live"


def test_live_401_cannot_close_mcp_authentication() -> None:
    errors = validate_mcp_not_closed_by_live_401(
        {
            "authentication": "Live initialize returned 401 Unauthorized so MCP is authenticated",
            "extension_points": "MCP transport locked down; 401 on all methods",
        },
        {"mcp"},
    )
    assert len(errors) == 2
    assert all("401" in error or "Unauthorized" in error for error in errors)


def test_live_401_note_passes_when_source_bind_is_cited() -> None:
    errors = validate_mcp_not_closed_by_live_401(
        {
            "authentication": (
                "Live URL returned 401; white-box review of _run_http shows bind "
                "0.0.0.0:8001 with no endpoint auth — filed separately."
            ),
            "extension_points": "Source review of stdio and HTTP transports complete.",
        },
        {"mcp"},
    )
    assert errors == []


def test_reported_coverage_without_finding_is_rejected() -> None:
    _record_impl(
        surface="https://api.example",
        risk_area="permissive CORS",
        outcome="reported",
        evidence="ACA-Origin reflects attacker origin.",
        agent_id="child-1",
        agent_name="CORS",
    )
    errors = validate_reported_coverage_has_findings(
        get_coverage_entries(),
        [{"title": "TLS verification disabled", "description": "ssl=False in client"}],
    )
    assert errors
    assert "permissive" in errors[0] or "cors" in errors[0].lower()


def test_reported_coverage_matches_filed_title() -> None:
    _record_impl(
        surface="https://api.example",
        risk_area="permissive CORS",
        outcome="reported",
        evidence="ACA-Origin reflects attacker origin.",
        agent_id="child-1",
        agent_name="CORS",
    )
    errors = validate_reported_coverage_has_findings(
        get_coverage_entries(),
        [
            {
                "title": "Permissive CORS reflects Origin",
                "description": "access-control-allow-origin",
            }
        ],
    )
    assert errors == []


class _FakeReport:
    def __init__(
        self,
        scan_config: dict[str, object],
        vulns: list[dict[str, object]] | None = None,
    ):
        self.scan_config = scan_config
        self.vulnerability_reports = vulns or []

    def get_baseline_finding_counts(self) -> dict[str, int]:
        return {}

    def update_scan_final_fields(self, **_kwargs: object) -> None:
        return None


def _standing_checklist(**overrides: str) -> dict[str, str]:
    base = {c: f"reviewed {c}, nothing of note found here" for c in REQUIRED_COVERAGE_CATEGORIES}
    base.update(overrides)
    return base


def test_finish_rejects_when_required_whitebox_mcp_agent_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    playbooks = required_playbooks_for({"mcp"}, has_source=True, has_live_url=False)
    scan_config = {
        "targets": [{"type": "repository", "details": {"cloned_repo_path": "/workspace/repo"}}],
        "detected_surfaces": ["mcp"],
        "required_playbooks": [playbook_to_dict(pb) for pb in playbooks],
    }
    monkeypatch.setattr(
        "strix.report.state.get_global_report_state",
        lambda: _FakeReport(scan_config),
    )
    checklist = _standing_checklist(
        authentication="Live 401 so the product authenticates MCP callers",
    )
    extras = extra_checklist_keys(playbooks, REQUIRED_COVERAGE_CATEGORIES)
    for key in extras:
        checklist[key] = f"reviewed {key} via live HTTP recon only"

    result = _do_finish(
        parent_id=None,
        executive_summary="summary",
        methodology="methodology",
        technical_analysis="analysis",
        recommendations="recommendations",
        coverage_checklist=checklist,
        agent_graph=_graph(
            {
                "name": "Live recon",
                "skills": ["httpx"],
                "task": "CORS and 401 against https://api.example",
            }
        ),
    )
    assert result["success"] is False
    joined = " ".join(result["errors"])
    assert "mcp_server" in joined
    assert "401" in joined or "Unauthorized" in joined


def test_validate_playbook_finish_combines_gates() -> None:
    playbooks = [
        next(
            item
            for item in required_playbooks_for({"mcp"}, has_source=True, has_live_url=False)
            if item.checklist_key == "mcp_server"
        )
    ]
    errors = validate_playbook_finish(
        scan_config={
            "detected_surfaces": ["mcp"],
            "required_playbooks": [playbook_to_dict(playbooks[0])],
        },
        coverage_checklist={
            "authentication": "All methods returned 401 Unauthorized; MCP is locked down",
        },
        agent_graph=_graph(),
        coverage_entries=[],
        vulnerability_reports=[],
    )
    assert any("mcp_server" in error for error in errors)
    assert any("401" in error or "Unauthorized" in error for error in errors)
