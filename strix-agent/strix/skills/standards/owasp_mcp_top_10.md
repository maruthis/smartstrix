---
name: owasp_mcp_top_10
description: OWASP MCP Top 10:2025 coverage map — spawn specialists for every MCP server/client category that has surface
---

# OWASP MCP Top 10:2025

Coverage index for Model Context Protocol servers and the apps that expose them. Spawn a specialist for **every** row that applies. Tag findings `OWASP MCP0x:2025` plus CWE.

This map is for **MCP server implementations and their transports**, not for checked-in coding-agent config files. Use `agent_mcp_config` for `CLAUDE.md` / `.cursor/mcp.json` / `SKILL.md`. Use this map when the tree contains `tools/call` handlers, a tool registry, FastMCP, or Streamable HTTP / SSE / stdio MCP transports.

Out of scope: the upstream SaaS the MCP server proxies to, unless that URL is also a listed scan target.

## Mandatory coverage

| ID | Category | Spawn with skills |
|---|---|---|
| MCP01:2025 | Token Mismanagement & Secret Exposure | `mcp_server`, `information_disclosure` |
| MCP02:2025 | Privilege Escalation via Scope Creep | `mcp_server`, `broken_function_level_authorization` |
| MCP03:2025 | Tool Poisoning | `mcp_server`, `agentic_system_security` |
| MCP04:2025 | Software Supply Chain Attacks | `dependency_cve_scanning` |
| MCP05:2025 | Command Injection & Execution | `rce`, `argument_injection` |
| MCP06:2025 | Intent Flow Subversion | `llm_prompt_injection`, `mcp_server` |
| MCP07:2025 | Insufficient Authentication & Authorization | `mcp_server`, `idor`, `authentication_jwt` |
| MCP08:2025 | Lack of Audit and Telemetry | `information_disclosure`, `mcp_server` |
| MCP09:2025 | Shadow MCP Servers | `agentic_system_security` |
| MCP10:2025 | Context Injection & Over-Sharing | `mcp_server`, `llm_prompt_injection`, `information_disclosure` |

## Spawn rules

- Always spawn `mcp_server` first on an MCP implementation with `review_mode='whitebox'` — it covers TLS-to-backend, unauthenticated `tools/call`, schema enforcement, destructive tools without confirm, bind address, and path-building from raw IDs. A live 401/CORS agent does not satisfy this row.
- MCP05: skip the RCE specialist only when there is no shell/exec/eval path in handlers (still grep for it; a clean grep is a coverage note, not a skip-before-looking)
- MCP04: the standing SCA agent already required by `coordination/root_agent` counts; do not spawn a second identical trivy pass
- Live URL in scope: POST JSON-RPC `initialize`, `tools/list`, and `tools/call` to that URL. A REST `401` on `/login` is not an MCP pentest
- When filing: `OWASP MCP0x:2025 — CWE-NNN — <one-line issue>`
