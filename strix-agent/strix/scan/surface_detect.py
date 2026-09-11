"""Cheap filesystem heuristics for scan-time surface detection."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:
    from collections.abc import Iterator


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
        "site-packages",
        "dist-packages",
    }
)
_CODE_SUFFIXES = frozenset({".py", ".ts", ".js", ".mjs", ".go", ".rs", ".java", ".rb"})
_CONFIG_SUFFIXES = frozenset({".yml", ".yaml", ".json", ".md", ".toml"})
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
_GRAPHQL_MARKERS = (
    "graphql",
    "GraphQL",
    "gql(",
    "graphene",
    "ariadne",
    "strawberry.federation",
)
_K8S_MARKERS = (
    "kind: Deployment",
    "kind: DaemonSet",
    "kind: StatefulSet",
    "kind: RoleBinding",
    "apiVersion: apps/",
    "apiVersion: rbac.authorization.k8s.io",
)
_CICD_FILENAMES = frozenset(
    {
        ".gitlab-ci.yml",
        "gitlab-ci.yml",
        "jenkinsfile",
        "azure-pipelines.yml",
        "bitbucket-pipelines.yml",
        ".travis.yml",
    }
)
_AGENT_CONFIG_FILENAMES = frozenset(
    {
        "claude.md",
        "agents.md",
        "skill.md",
        "mcp.json",
    }
)
_MAX_FILES = 800
_AI_SURFACES = frozenset({"mcp", "llm", "agentic"})
_ALL_SURFACES = frozenset(
    {"mcp", "llm", "agentic", "graphql", "cicd", "kubernetes", "agent_mcp_config"}
)


def source_paths_from_local(local_sources: list[dict[str, Any]] | None) -> list[str]:
    """Absolute trees the harness mounted for this scan."""
    return [
        str(source["source_path"])
        for source in local_sources or []
        if isinstance(source, dict) and source.get("source_path")
    ]


def _should_skip(path: Path) -> bool:
    return any(part in _SKIP_DIR_NAMES for part in path.parts)


def _iter_text_files(source_paths: list[str], *, max_files: int) -> Iterator[tuple[Path, str]]:
    seen = 0
    for raw in source_paths:
        root = Path(raw)
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if seen >= max_files:
                return
            if path.is_dir() or _should_skip(path):
                continue
            suffix = path.suffix.lower()
            name = path.name.lower()
            is_code = suffix in _CODE_SUFFIXES
            is_config = (
                suffix in _CONFIG_SUFFIXES or name in _CICD_FILENAMES or name == "dockerfile"
            )
            if not is_code and not is_config:
                continue
            seen += 1
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            yield path, text


def _filename_surfaces(path: Path) -> set[str]:
    name = path.name.lower()
    parts_lower = {part.lower() for part in path.parts}
    found: set[str] = set()
    if name in _CICD_FILENAMES or name == "jenkinsfile":
        found.add("cicd")
    if (
        ".github" in parts_lower
        and "workflows" in parts_lower
        and path.suffix.lower()
        in {
            ".yml",
            ".yaml",
        }
    ):
        found.add("cicd")
    if name in _AGENT_CONFIG_FILENAMES:
        found.add("agent_mcp_config")
    if name == "dockerfile" or name.startswith("dockerfile."):
        found.add("kubernetes")
    return found


def detect_surfaces(source_paths: list[str], *, max_files: int = _MAX_FILES) -> set[str]:
    """Return every cheaply-detected playbook surface in local trees."""
    found: set[str] = set()
    for path, text in _iter_text_files(source_paths, max_files=max_files):
        found.update(_filename_surfaces(path))
        if "mcp" not in found and any(marker in text for marker in _MCP_MARKERS):
            found.add("mcp")
            found.add("llm")
            found.add("agentic")
        if "llm" not in found and any(marker in text for marker in _LLM_MARKERS):
            found.add("llm")
        if "agentic" not in found and any(marker in text for marker in _AGENTIC_MARKERS):
            found.add("agentic")
        if "graphql" not in found and any(marker in text for marker in _GRAPHQL_MARKERS):
            found.add("graphql")
        if "kubernetes" not in found and any(marker in text for marker in _K8S_MARKERS):
            found.add("kubernetes")
        if found >= _ALL_SURFACES:
            break
    return found


def detect_ai_surfaces(source_paths: list[str], *, max_files: int = _MAX_FILES) -> set[str]:
    """Return ``{"mcp", "llm", "agentic"}`` subsets found in local trees."""
    return detect_surfaces(source_paths, max_files=max_files) & _AI_SURFACES


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
    paths = source_paths_from_local(local_sources)
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
