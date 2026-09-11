"""Required specialist playbooks derived from detected surfaces.

``finish_scan`` refuses to complete until each required playbook has a
non-root agent that (1) carries a matching skill, (2) matches the required
review mode, and (3) recorded coverage for that class. Live HTTP recon
cannot satisfy a white-box playbook. A coverage row with outcome
``reported`` must match a filed vulnerability report.

This is machine-enforced. Prompt text telling the root to spawn specialists
is not enough — the GitLab MCP regressions showed the root optimizing for
the ``live_http`` checklist and skipping source review.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

from strix.report.coverage import (
    _SKILL_PHRASINGS,
    _entry_is_about,
    _normalized,
    _skill_leaf,
    _skill_phrasings,
    agents_from_graph,
)
from strix.scan.surface_detect import detect_surfaces, source_paths_from_local


VALID_REVIEW_MODES: frozenset[str] = frozenset({"whitebox", "live", "both"})

_LIVE_HINTS = re.compile(
    r"\b("
    r"httpx|live[- ]?(?:http|url|site|recon)|cors|preflight|browser|"
    r"https?://|black-?box|dynamic test|connectivity|katana|ffuf|nuclei"
    r")\b",
    re.IGNORECASE,
)
_WHITEBOX_HINTS = re.compile(
    r"\b("
    r"white-?box|source(?:-aware)?|repositor(?:y|ies)|code review|sast|"
    r"stdio|bind address|0\.0\.0\.0|tool registry|handler auth|"
    r"app/|read the (?:code|tree|handler|source)"
    r")\b",
    re.IGNORECASE,
)
_LIVE_TOOL_SKILLS = frozenset(
    {"httpx", "katana", "ffuf", "nuclei", "agent_browser", "sqlmap", "nmap", "naabu"}
)
_MCP_SOURCE_HINTS = re.compile(
    r"\b("
    r"0\.0\.0\.0|bind address|stdio|handler auth|endpoint auth|"
    r"run_full|_run_http|source review|white-?box|listen(?:er)?|"
    r"no (?:app-layer |application )?auth|unauthenticated (?:http|mcp|transport)"
    r")\b",
    re.IGNORECASE,
)
_401_RECON = re.compile(
    r"\b(401|unauthorized|www-authenticate|authentication required)\b",
    re.IGNORECASE,
)
_REPORT_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "the",
        "for",
        "from",
        "with",
        "this",
        "that",
        "into",
        "over",
        "via",
        "on",
        "in",
        "of",
        "to",
        "or",
        "at",
        "by",
        "as",
        "is",
        "was",
        "be",
        "not",
        "no",
        "found",
        "issue",
        "test",
        "tested",
        "review",
        "reviewed",
        "endpoint",
        "file",
        "code",
        "source",
        "live",
        "http",
        "https",
        "url",
        "api",
        "app",
        "server",
    }
)

_PLAYBOOK_PHRASINGS: dict[str, tuple[str, ...]] = {
    **_SKILL_PHRASINGS,
    "llm_applications": (
        "llm application",
        "rag",
        "embedding",
        "model provider",
        "prompt injection",
        "llm",
    ),
    "graphql": ("graphql",),
    "kubernetes": ("kubernetes", "k8s", "helm", "dockerfile"),
    "oauth": ("oauth", "oidc", "openid"),
    "source_aware_sast": ("sast", "source review", "static analysis"),
}


@dataclass(frozen=True)
class RequiredPlaybook:
    """One specialist that ``finish_scan`` will demand evidence for."""

    skills: tuple[str, ...]
    review_mode: str
    checklist_key: str
    label: str
    spawn_hint: str

    def __post_init__(self) -> None:
        if self.review_mode not in VALID_REVIEW_MODES:
            raise ValueError(f"invalid review_mode {self.review_mode!r}")
        if not self.skills:
            raise ValueError("RequiredPlaybook.skills cannot be empty")


def _pb(
    skills: str | tuple[str, ...],
    review_mode: str,
    checklist_key: str,
    label: str,
    spawn_hint: str,
) -> RequiredPlaybook:
    skill_tuple = (skills,) if isinstance(skills, str) else skills
    return RequiredPlaybook(
        skills=skill_tuple,
        review_mode=review_mode,
        checklist_key=checklist_key,
        label=label,
        spawn_hint=spawn_hint,
    )


# Detected surface → playbooks that MUST run. MCP also implies the LLM and
# agentic rows via surface_detect (an MCP server is a tool-calling agent).
SURFACE_PLAYBOOKS: dict[str, tuple[RequiredPlaybook, ...]] = {
    "mcp": (
        _pb(
            "mcp_server",
            "whitebox",
            "mcp_server",
            "MCP server (source)",
            "Read the handler, registry, transports, bind address, and tool "
            "authz in app/. Live httpx is not this row.",
        ),
    ),
    "llm": (
        _pb(
            "llm_prompt_injection",
            "whitebox",
            "llm_prompt_injection",
            "LLM prompt injection (source)",
            "Trace every untrusted string into a model call (direct, RAG, tool results).",
        ),
        _pb(
            "llm_applications",
            "whitebox",
            "llm_applications",
            "LLM application architecture (source)",
            "Map provider calls, embeddings, output sinks, and OWASP LLM01-LLM10 rows.",
        ),
        _pb(
            "ai_ml_governance",
            "whitebox",
            "ai_ml_governance",
            "AI/ML governance (source)",
            "Provider retention, prompt logs, PII egress, guardrails outside the system prompt.",
        ),
    ),
    "agentic": (
        _pb(
            "agentic_system_security",
            "whitebox",
            "agentic_system_security",
            "Agentic system security (source)",
            "Tool/MCP authority, confirmation on destructive tools, confused-deputy paths.",
        ),
    ),
    "graphql": (
        _pb(
            "graphql",
            "whitebox",
            "graphql",
            "GraphQL (source)",
            "Introspection, authz on mutations, batching, nested query cost.",
        ),
    ),
    "cicd": (
        _pb(
            "ci_cd_injection",
            "whitebox",
            "ci_cd_injection",
            "CI/CD injection (source)",
            "Workflow expression injection and AI-agent steps in pipeline YAML.",
        ),
    ),
    "kubernetes": (
        _pb(
            "kubernetes",
            "whitebox",
            "kubernetes",
            "Kubernetes / containers (source)",
            "Manifests, privileged pods, secrets mounts, and image pinning.",
        ),
    ),
    "agent_mcp_config": (
        _pb(
            "agent_mcp_config",
            "whitebox",
            "agent_mcp_config",
            "Agent MCP client config (source)",
            "CLAUDE.md / mcp.json / SKILL.md — unpinned servers and hook injection.",
        ),
    ),
}

STANDING_WHITEBOX_PLAYBOOKS: tuple[RequiredPlaybook, ...] = (
    _pb(
        ("idor", "broken_function_level_authorization", "path_traversal_lfi_rfi"),
        "whitebox",
        "access_control",
        "Access control (source)",
        "Spawn idor / BFLA / path-traversal against the repository — not only live 401s.",
    ),
    _pb(
        ("authentication_jwt", "session_management", "oauth"),
        "whitebox",
        "authentication",
        "Authentication (source)",
        "Read token/session/OAuth implementation. A gateway 401 is not this review.",
    ),
    _pb(
        ("sql_injection", "xss", "rce", "ssrf", "nosql_injection", "ssti", "header_injection"),
        "whitebox",
        "injection",
        "Injection (source)",
        "White-box injection/SSRF review of first-party handlers.",
    ),
)

MCP_LIVE_PLAYBOOK = _pb(
    "mcp_server",
    "live",
    "mcp_live",
    "MCP protocol (live)",
    "POST JSON-RPC initialize / tools/list / tools/call on the listed URL. "
    "A REST 401 is not this row. review_mode='live' (or 'both').",
)


def playbook_to_dict(playbook: RequiredPlaybook) -> dict[str, Any]:
    payload = asdict(playbook)
    payload["skills"] = list(playbook.skills)
    return payload


def playbook_from_dict(raw: dict[str, Any]) -> RequiredPlaybook | None:
    skills_raw = raw.get("skills")
    if not isinstance(skills_raw, list) or not skills_raw:
        return None
    skills = tuple(str(skill) for skill in skills_raw if str(skill).strip())
    if not skills:
        return None
    try:
        return RequiredPlaybook(
            skills=skills,
            review_mode=str(raw.get("review_mode") or "whitebox"),
            checklist_key=str(raw.get("checklist_key") or skills[0]),
            label=str(raw.get("label") or skills[0]),
            spawn_hint=str(raw.get("spawn_hint") or ""),
        )
    except ValueError:
        return None


def required_playbooks_for(
    surfaces: set[str],
    *,
    has_source: bool,
    has_live_url: bool,
) -> list[RequiredPlaybook]:
    """Deduped playbook list for this scan's surfaces and target types."""
    found: list[RequiredPlaybook] = []
    seen: set[tuple[tuple[str, ...], str, str]] = set()

    def _add(playbook: RequiredPlaybook) -> None:
        key = (playbook.skills, playbook.review_mode, playbook.checklist_key)
        if key in seen:
            return
        seen.add(key)
        found.append(playbook)

    if has_source:
        for playbook in STANDING_WHITEBOX_PLAYBOOKS:
            _add(playbook)
        for surface in sorted(surfaces):
            for playbook in SURFACE_PLAYBOOKS.get(surface, ()):
                _add(playbook)
    if has_live_url and "mcp" in surfaces:
        _add(MCP_LIVE_PLAYBOOK)
    return found


def attach_required_playbooks(
    scan_config: dict[str, Any],
    local_sources: list[dict[str, Any]] | None,
) -> list[RequiredPlaybook]:
    """Detect surfaces, persist required playbooks on ``scan_config``, return them."""
    paths = source_paths_from_local(local_sources)
    surfaces = detect_surfaces(paths)
    raw_targets = scan_config.get("targets")
    targets = raw_targets if isinstance(raw_targets, list) else []
    has_live_url = any(
        isinstance(target, dict) and target.get("type") == "web_application" for target in targets
    )
    playbooks = required_playbooks_for(
        surfaces,
        has_source=bool(paths),
        has_live_url=has_live_url,
    )
    scan_config["detected_surfaces"] = sorted(surfaces)
    scan_config["required_playbooks"] = [playbook_to_dict(item) for item in playbooks]
    return playbooks


def playbooks_from_scan_config(scan_config: dict[str, Any] | None) -> list[RequiredPlaybook]:
    raw = (scan_config or {}).get("required_playbooks")
    if not isinstance(raw, list):
        return []
    return [
        parsed for item in raw if isinstance(item, dict) and (parsed := playbook_from_dict(item))
    ]


def matching_required_playbook(
    playbooks: list[RequiredPlaybook],
    *,
    skills: list[str],
    review_mode: str = "",
    name: str = "",
    task: str = "",
) -> RequiredPlaybook | None:
    """Return the first required playbook this agent is assigned to satisfy."""
    if not playbooks:
        return None
    agent = {
        "skills": skills,
        "review_mode": review_mode,
        "agent_name": name,
        "task": task,
    }
    for playbook in playbooks:
        if _agent_carries(agent, playbook.skills) and _mode_satisfies(
            classify_review_mode(agent), playbook.review_mode
        ):
            return playbook
    return None


def extra_checklist_keys(
    playbooks: list[RequiredPlaybook], standing: tuple[str, ...]
) -> tuple[str, ...]:
    """Checklist keys that are not already in the standing finish_scan list."""
    standing_set = set(standing)
    extras: list[str] = []
    for playbook in playbooks:
        if playbook.checklist_key in standing_set or playbook.checklist_key in extras:
            continue
        extras.append(playbook.checklist_key)
    return tuple(extras)


def classify_review_mode(agent: dict[str, Any]) -> str:
    """Return ``whitebox`` / ``live`` / ``both`` for a flattened agent record."""
    declared = str(agent.get("review_mode") or "").strip().lower()
    if declared in VALID_REVIEW_MODES:
        return declared
    text = f"{agent.get('agent_name') or ''} {agent.get('task') or ''}"
    skills = {_skill_leaf(skill) for skill in agent.get("skills") or []}
    has_live = bool(_LIVE_HINTS.search(text)) or bool(skills & _LIVE_TOOL_SKILLS)
    has_whitebox = bool(_WHITEBOX_HINTS.search(text)) or "source_aware_sast" in skills
    if has_live and has_whitebox:
        return "both"
    if has_live:
        return "live"
    return "whitebox"


def _mode_satisfies(actual: str, required: str) -> bool:
    if actual == "both":
        return True
    return actual == required


def _agent_carries(agent: dict[str, Any], skills: tuple[str, ...]) -> bool:
    held = {_skill_leaf(skill) for skill in agent.get("skills") or []}
    return bool(held & {_skill_leaf(skill) for skill in skills})


def _coverage_matches_playbook(entries: list[dict[str, Any]], playbook: RequiredPlaybook) -> bool:
    for skill in playbook.skills:
        phrasings = (
            [_normalized(phrase).split() for phrase in _PLAYBOOK_PHRASINGS[skill]]
            if skill in _PLAYBOOK_PHRASINGS
            else _skill_phrasings(skill)
        )
        phrasings = [terms for terms in phrasings if terms]
        if any(_entry_is_about(entry, phrasings) for entry in entries):
            return True
    return False


def _open_required_follow_ups(
    entries: list[dict[str, Any]], playbook: RequiredPlaybook
) -> list[dict[str, Any]]:
    open_rows: list[dict[str, Any]] = []
    for skill in playbook.skills:
        phrasings = (
            [_normalized(phrase).split() for phrase in _PLAYBOOK_PHRASINGS[skill]]
            if skill in _PLAYBOOK_PHRASINGS
            else _skill_phrasings(skill)
        )
        phrasings = [terms for terms in phrasings if terms]
        for entry in entries:
            if entry.get("outcome") != "needs_follow_up":
                continue
            if _entry_is_about(entry, phrasings):
                open_rows.append(entry)
    return open_rows


def validate_required_playbook_agents(
    playbooks: list[RequiredPlaybook],
    agent_graph: dict[str, Any],
    coverage_entries: list[dict[str, Any]],
) -> list[str]:
    """Reject finish when a required specialist never ran or never recorded coverage."""
    agents = agents_from_graph(agent_graph)
    children = [agent for agent in agents if not agent.get("is_root")]
    errors: list[str] = []
    for playbook in playbooks:
        matching = [
            agent
            for agent in children
            if _agent_carries(agent, playbook.skills)
            and _mode_satisfies(classify_review_mode(agent), playbook.review_mode)
        ]
        skill_list = ", ".join(playbook.skills)
        if not matching:
            errors.append(
                f"Required playbook '{playbook.label}' was not assigned to a "
                f"{playbook.review_mode} specialist (skills: {skill_list}). "
                f"{playbook.spawn_hint} Live HTTP agents do not satisfy a "
                "white-box playbook. Pass review_mode on create_agent."
            )
            continue
        if not _coverage_matches_playbook(coverage_entries, playbook):
            names = ", ".join(agent["agent_name"] for agent in matching)
            errors.append(
                f"Required playbook '{playbook.label}' ran ({names}) "
                f"but no coverage entry records {skill_list}. Call record_coverage "
                "for that class before finish_scan."
            )
        errors.extend(
            (
                f"Required playbook '{playbook.label}' still has a needs_follow_up "
                f"coverage row ({row.get('surface', '')} / {row.get('risk_area', '')}). "
                "Close it or spawn the follow-up before finishing."
            )
            for row in _open_required_follow_ups(coverage_entries, playbook)
        )
    return errors


def validate_mcp_not_closed_by_live_401(
    coverage_checklist: dict[str, str],
    surfaces: set[str],
) -> list[str]:
    """A hostname 401 is not proof the MCP product authenticates."""
    if "mcp" not in surfaces:
        return []
    errors: list[str] = []
    for category in ("authentication", "extension_points"):
        note = coverage_checklist.get(category, "")
        if not _401_RECON.search(note):
            continue
        if _MCP_SOURCE_HINTS.search(note):
            continue
        errors.append(
            f"coverage_checklist['{category}'] treats a live 401/Unauthorized as "
            "closing MCP authentication. That is a gateway/proxy in front of the "
            "host, not the MCP bind/handler/stdio gate. Review source for "
            "0.0.0.0 listeners, missing endpoint auth, and stdio trust, then "
            "state that white-box result in the note."
        )
    return errors


def _report_haystack(reports: list[dict[str, Any]]) -> str:
    chunks: list[str] = []
    for report in reports:
        chunks.append(str(report.get("title") or ""))
        chunks.append(str(report.get("vulnerability_type") or ""))
        chunks.append(str(report.get("cwe") or ""))
        description = str(report.get("description") or "")
        chunks.append(description[:800])
    return _normalized(" ".join(chunks))


def _meaningful_tokens(text: str) -> list[str]:
    return [
        token
        for token in _normalized(text).split()
        if len(token) >= 3 and token not in _REPORT_STOPWORDS
    ]


def validate_reported_coverage_has_findings(
    coverage_entries: list[dict[str, Any]],
    vulnerability_reports: list[dict[str, Any]],
) -> list[str]:
    """``outcome=reported`` is a claim that a finding was filed. Enforce it."""
    reported = [entry for entry in coverage_entries if entry.get("outcome") == "reported"]
    if not reported:
        return []
    haystack = _report_haystack(vulnerability_reports)
    errors: list[str] = []
    for entry in reported:
        surface = str(entry.get("surface") or "")
        risk_area = str(entry.get("risk_area") or "")
        tokens = _meaningful_tokens(f"{risk_area} {surface}")
        if not vulnerability_reports:
            errors.append(
                f"coverage '{surface}' / '{risk_area}' is outcome=reported but "
                "no vulnerability was filed. Call create_vulnerability_report "
                "(or create_dependency_report for a CVE) or change the outcome."
            )
            continue
        if tokens and not any(token in haystack for token in tokens):
            errors.append(
                f"coverage '{surface}' / '{risk_area}' is outcome=reported but "
                "no filed finding mentions that class. File it with "
                "create_vulnerability_report or correct the coverage outcome. "
                "Executive-summary prose is not a finding."
            )
    return errors


def validate_playbook_finish(
    *,
    scan_config: dict[str, Any] | None,
    coverage_checklist: dict[str, str],
    agent_graph: dict[str, Any],
    coverage_entries: list[dict[str, Any]],
    vulnerability_reports: list[dict[str, Any]],
) -> list[str]:
    """All machine playbook gates that ``finish_scan`` must apply."""
    playbooks = playbooks_from_scan_config(scan_config)
    raw_surfaces = (scan_config or {}).get("detected_surfaces")
    surfaces = {str(item) for item in raw_surfaces} if isinstance(raw_surfaces, list) else set()
    errors: list[str] = []
    errors.extend(validate_required_playbook_agents(playbooks, agent_graph, coverage_entries))
    errors.extend(validate_mcp_not_closed_by_live_401(coverage_checklist, surfaces))
    errors.extend(validate_reported_coverage_has_findings(coverage_entries, vulnerability_reports))
    return errors
