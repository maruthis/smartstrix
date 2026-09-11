from pathlib import Path

from app.coverage_summary import (
    MOCK_COVERAGE,
    empty_real_coverage,
    read_coverage_summary,
    summarize_coverage_document,
)


def test_summarize_coverage_document_extracts_gaps_and_agents():
    summary = summarize_coverage_document(
        {
            "completeness": {
                "complete": False,
                "scan_status": "running",
                "exit_reason": None,
                "caveats": ["finish_scan was never called"],
            },
            "machine_observed": {
                "agents": [
                    {
                        "agent_id": "a1",
                        "agent_name": "mcp-whitebox",
                        "status": "stopped",
                        "skills": ["mcp_server"],
                        "is_root": False,
                    }
                ]
            },
            "gaps": [
                {
                    "kind": "skill_gap",
                    "risk_area": "mcp_server",
                    "surface": "tools",
                    "detail": "No ledger row",
                }
            ],
            "summary": {"surfaces_reviewed": 2, "findings_filed": 1, "gaps": 1},
        }
    )
    assert summary["mode"] == "real"
    assert summary["finish_scan"] is False
    assert summary["caveats"] == ["finish_scan was never called"]
    assert summary["gaps"][0]["risk_area"] == "mcp_server"
    assert summary["agents"][0]["agent_name"] == "mcp-whitebox"


def test_read_coverage_summary_returns_none_for_missing_or_corrupt(tmp_path: Path):
    assert read_coverage_summary(tmp_path) is None
    (tmp_path / "coverage.json").write_text("not-json", encoding="utf-8")
    assert read_coverage_summary(tmp_path) is None


def test_empty_real_coverage_and_mock_are_honest():
    empty = empty_real_coverage(finish_scan=False)
    assert empty["complete"] is False
    assert empty["exit_reason"] == "finish_scan_missing"
    assert MOCK_COVERAGE["mode"] == "mock"
    assert "canned samples" in MOCK_COVERAGE["caveats"][0]
