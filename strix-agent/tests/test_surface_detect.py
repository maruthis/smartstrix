from pathlib import Path

from strix.scan.surface_detect import (
    detect_ai_surfaces,
    ensure_detected_standard_skills,
    ensure_mcp_standard_skill,
    looks_like_mcp_server,
)


def test_looks_like_mcp_server_detects_tools_call(tmp_path: Path) -> None:
    (tmp_path / "handler.py").write_text("async def handle():\n    return await registry.call('tools/call')\n")
    assert looks_like_mcp_server([str(tmp_path)]) is True


def test_looks_like_mcp_server_ignores_client_config_only(tmp_path: Path) -> None:
    (tmp_path / "mcp.json").write_text('{"mcpServers": {}}')
    (tmp_path / "CLAUDE.md").write_text("Use the MCP tools.")
    assert looks_like_mcp_server([str(tmp_path)]) is False


def test_ensure_mcp_standard_skill_appends_llm_and_agentic_maps(tmp_path: Path) -> None:
    (tmp_path / "server.py").write_text("from mcp.server import Server\n")
    skills = ensure_mcp_standard_skill(["standards/owasp_top_10"], [{"source_path": str(tmp_path)}])
    assert skills == [
        "standards/owasp_top_10",
        "standards/owasp_mcp_top_10",
        "standards/owasp_llm_top_10",
        "standards/owasp_agentic_top_10",
    ]
    again = ensure_mcp_standard_skill(skills, [{"source_path": str(tmp_path)}])
    assert again == skills


def test_ensure_mcp_standard_skill_noop_without_mcp(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("print('hello')\n")
    skills = ensure_mcp_standard_skill(["standards/owasp_top_10"], [{"source_path": str(tmp_path)}])
    assert skills == ["standards/owasp_top_10"]


def test_langchain_app_loads_llm_map_not_mcp(tmp_path: Path) -> None:
    (tmp_path / "chain.py").write_text("from langchain.chat_models import ChatOpenAI\n")
    surfaces = detect_ai_surfaces([str(tmp_path)])
    assert surfaces == {"llm"}
    skills = ensure_detected_standard_skills(["standards/owasp_top_10"], [{"source_path": str(tmp_path)}])
    assert "standards/owasp_llm_top_10" in skills
    assert "standards/owasp_mcp_top_10" not in skills
