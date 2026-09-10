"""Allowlist of SaaS-selectable standards coverage maps.

Kept here (not imported from ``strix.skills``) so mock-mode still works
without the optional ``real-scan`` extra. Names must match files under
``strix/skills/standards/<name>.md``.
"""

from __future__ import annotations

from fastapi import HTTPException, status

STANDARD_SKILL_NAMES: tuple[str, ...] = (
    "owasp_top_10",
    "owasp_asvs",
    "owasp_api_top_10",
    "owasp_mcp_top_10",
    "owasp_llm_top_10",
    "owasp_agentic_top_10",
    "nist_ai_rmf",
    "pci_dss",
    "nist_ssdf",
)

STANDARD_SKILLS: frozenset[str] = frozenset(STANDARD_SKILL_NAMES)

DEFAULT_STANDARD_SKILLS: list[str] = ["owasp_top_10"]

STANDARD_SKILL_CATALOG: list[dict[str, str]] = [
    {
        "name": "owasp_top_10",
        "label": "OWASP Top 10:2025",
        "description": (
            "Application security coverage map — spawn a specialist per testable category."
        ),
    },
    {
        "name": "owasp_asvs",
        "label": "OWASP ASVS (L1/L2)",
        "description": (
            "Testable ASVS chapters: auth, session, access control, validation, crypto, config."
        ),
    },
    {
        "name": "owasp_api_top_10",
        "label": "OWASP API Security Top 10",
        "description": (
            "API1-API10: object/function authz, mass assignment, rate limits, SSRF, inventory."
        ),
    },
    {
        "name": "owasp_mcp_top_10",
        "label": "OWASP MCP Top 10",
        "description": (
            "MCP01-MCP10: tool authz, schema enforcement, secret exposure, prompt injection via tools."
        ),
    },
    {
        "name": "owasp_llm_top_10",
        "label": "OWASP LLM Top 10",
        "description": (
            "LLM01-LLM10: injection, provider data leakage, excessive agency, RAG/tenant isolation."
        ),
    },
    {
        "name": "owasp_agentic_top_10",
        "label": "OWASP Agentic Top 10",
        "description": (
            "ASI01-ASI10: goal hijack, tool misuse, agent supply chain, memory poisoning."
        ),
    },
    {
        "name": "nist_ai_rmf",
        "label": "NIST AI RMF (technical)",
        "description": (
            "Testable Map/Measure/Manage: model identity, data egress, fail-closed guardrails. Paperwork out of scope."
        ),
    },
    {
        "name": "pci_dss",
        "label": "PCI DSS 4.0 (technical)",
        "description": (
            "Testable requirements 2, 4, 6, 8, 11. Policy and physical controls are out of scope."
        ),
    },
    {
        "name": "nist_ssdf",
        "label": "NIST SSDF / 800-53",
        "description": (
            "Technical overlay (SA, SI, SC, IA, AC). Governance paperwork is out of scope."
        ),
    },
]


def normalize_standard_skills(skills: list[str] | None) -> list[str]:
    """Return a de-duplicated allowlisted list, defaulting to OWASP Top 10.

    Raises HTTP 400 ``invalid_skills`` when the caller sent a non-empty list
    that contains an unknown name.
    """
    if not skills:
        return list(DEFAULT_STANDARD_SKILLS)
    seen: list[str] = []
    for name in skills:
        if not isinstance(name, str) or not name.strip():
            continue
        trimmed = name.strip()
        if trimmed not in STANDARD_SKILLS:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="invalid_skills")
        if trimmed not in seen:
            seen.append(trimmed)
    if not seen:
        return list(DEFAULT_STANDARD_SKILLS)
    return seen


def to_engine_skills(skills: list[str] | None) -> list[str]:
    """Qualify persisted names as ``standards/<name>`` for ``run_strix_scan``.

    Unknown names are dropped (rows predating validation, or a null JSON
    column after a schema backfill). An empty result falls back to OWASP.
    """
    names = [name for name in (skills or []) if name in STANDARD_SKILLS]
    if not names:
        names = list(DEFAULT_STANDARD_SKILLS)
    return [f"standards/{name}" for name in names]
