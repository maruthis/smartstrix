"""Cheap filesystem heuristics for scan-time surface detection."""

from __future__ import annotations

from pathlib import Path
from typing import Any

_SKIP_DIR_NAMES = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        ".venv",
        "venv",
        "node_modules",
        "__pycache__",
        "dist",
        "build",
        ".tox",
        ".mypy_cache",
    }
)
_CODE_SUFFIXES = frozenset({".py", ".ts", ".js", ".mjs", ".go", ".rs", ".java", ".rb"})
_MCP_MARKERS = (
    "tools/call",
    "FastMCP",
    "mcp.server",
    "modelcontextprotocol",
    "StatelessHandler",
    "ToolRegistry",
    "StreamableHTTP",
)
_LLM_MARKERS = (
    "from openai",
    "import openai",
    "from anthropic",
    "import litellm",
    "ChatOpenAI",
    "AzureOpenAI",
    "google.generativeai",
    "openai.OpenAI",
    "from langchain",
    "import langchain",
    "llama_index",
    "chromadb",
    "from pinecone",
    "text-embedding",
    "ChatCompletion",
    "vertexai",
    "huggingface_hub",
    "trust_remote_code",
)
_AGENTIC_MARKERS = (
    "langgraph",
    "crewai",
    "autogen",
    "AgentExecutor",
    "create_react_agent",
    "tool_calls",
    "function_call",
    "bind_tools",
)
_MAX_FILES = 800
_ALL_SURFACES = frozenset({"mcp", "llm", "agentic"})


def _iter_code_files(source_paths: list[str], *, max_files: int):
    seen = 0
    for raw in source_paths:
        root = Path(raw)
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if seen >= max_files:
                return
            if path.is_dir():
                continue
            if any(part in _SKIP_DIR_NAMES for part in path.parts):
                continue
            if path.suffix.lower() not in _CODE_SUFFIXES:
                continue
            seen += 1
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            yield text


def detect_ai_surfaces(source_paths: list[str], *, max_files: int = _MAX_FILES) -> set[str]:
    """Return ``{"mcp", "llm", "agentic"}`` subsets found in local trees."""
    found: set[str] = set()
    for text in _iter_code_files(source_paths, max_files=max_files):
        if "mcp" not in found and any(marker in text for marker in _MCP_MARKERS):
            found.add("mcp")
            found.add("llm")
            found.add("agentic")
        if "llm" not in found and any(marker in text for marker in _LLM_MARKERS):
            found.add("llm")
        if "agentic" not in found and any(marker in text for marker in _AGENTIC_MARKERS):
            found.add("agentic")
        if found >= _ALL_SURFACES:
            break
    return found


def looks_like_mcp_server(source_paths: list[str], *, max_files: int = _MAX_FILES) -> bool:
    """True when a local tree looks like an MCP *server* implementation.

    Client config files (``.cursor/mcp.json``, ``CLAUDE.md``) are not enough —
    those are ``agent_mcp_config`` surface. This looks for protocol handlers.
    """
    return "mcp" in detect_ai_surfaces(source_paths, max_files=max_files)


def _append_standard(skills: list[str], qualified: str) -> list[str]:
    short = qualified.rsplit("/", 1)[-1]
    already = {skill.strip() for skill in skills} & {qualified, short}
    if already:
        return skills
    return [*skills, qualified]


def ensure_detected_standard_skills(
    skills: list[str], local_sources: list[dict[str, Any]] | None
) -> list[str]:
    """Append MCP / LLM / agentic coverage maps when those surfaces exist."""
    paths = [
        str(source["source_path"])
        for source in local_sources or []
        if isinstance(source, dict) and source.get("source_path")
    ]
    surfaces = detect_ai_surfaces(paths)
    next_skills = list(skills)
    if "mcp" in surfaces:
        next_skills = _append_standard(next_skills, "standards/owasp_mcp_top_10")
    if "llm" in surfaces:
        next_skills = _append_standard(next_skills, "standards/owasp_llm_top_10")
    if "agentic" in surfaces:
        next_skills = _append_standard(next_skills, "standards/owasp_agentic_top_10")
    return next_skills


def ensure_mcp_standard_skill(
    skills: list[str], local_sources: list[dict[str, Any]] | None
) -> list[str]:
    """Append the MCP Top 10 coverage map when the tree is an MCP server."""
    return ensure_detected_standard_skills(skills, local_sources)
