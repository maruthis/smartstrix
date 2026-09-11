from strix.known_defects import GITLAB_MCP_VAPT, score_findings


def test_gitlab_mcp_vapt_scores_baseline_titles() -> None:
    findings = [
        {"title": "Service binds on all interfaces (0.0.0.0 / ::)"},
        {"title": "HTTP request headers logged at runtime"},
        {"title": "Unbounded TCP readexactly without a max size"},
        {"title": "audit_tool_execution is defined but never called"},
    ]
    score = score_findings(findings, skills=["owasp_mcp_top_10"])
    assert score["applicable"] is True
    assert score["checklist_id"] == GITLAB_MCP_VAPT.checklist_id
    assert score["matched"] == 4
    assert score["missed"] == 6
    assert score["total"] == 10
    hits = {item["id"] for item in score["items"] if item["status"] == "hit"}
    assert hits == {"V1", "V3", "V4", "V9"}


def test_checklist_not_applicable_without_mcp_signal() -> None:
    score = score_findings([{"title": "SQL injection in search"}], skills=["owasp_top_10"])
    assert score["applicable"] is False
    assert score["matched"] == 0


def test_unknown_checklist_id() -> None:
    score = score_findings([], checklist_id="does-not-exist")
    assert score["applicable"] is False
    assert score["error"] == "unknown_checklist"
