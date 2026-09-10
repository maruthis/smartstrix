---
name: owasp_agentic_top_10
description: OWASP Top 10 for Agentic Applications 2026 coverage map — spawn specialists for ASI01-ASI10 when the target can plan, use tools, or act
---

# OWASP Agentic Top 10:2026

Coverage index for systems that **plan and act** (tools, MCP, peer agents, memory, code execution). Spawn a specialist for every row with surface. Tag findings `OWASP ASI0x:2026` plus CWE.

This is not a duplicate of `owasp_llm_top_10`. LLM01 is instruction/data confusion in a model call. ASI01 is the agent’s **goal/plan** being redirected so it uses its existing tools toward an attacker objective.

**Out of scope:** speculative “the model might one day go rogue” without a control you can test (self-modification, unsupervised tool install, missing kill switch).

## Mandatory coverage

| ID | Category | Spawn with skills |
|---|---|---|
| ASI01:2026 | Agent Goal Hijack | `llm_prompt_injection`, `agentic_system_security` |
| ASI02:2026 | Tool Misuse and Exploitation | `mcp_server`, `agentic_system_security`, `broken_function_level_authorization` |
| ASI03:2026 | Identity and Privilege Abuse | `idor`, `authentication_jwt`, `agentic_system_security` |
| ASI04:2026 | Agentic Supply Chain | `dependency_cve_scanning`, `npx_confusion`, `agent_mcp_config` |
| ASI05:2026 | Unexpected Code Execution | `rce`, `argument_injection`, `insecure_deserialization` |
| ASI06:2026 | Memory and Context Poisoning | `llm_applications`, `ai_ml_governance` |
| ASI07:2026 | Insecure Inter-Agent Communication | `agentic_system_security`, `authentication_jwt` |
| ASI08:2026 | Cascading Failures | `business_logic`, `unrestricted_resource_consumption` |
| ASI09:2026 | Human-Agent Trust Exploitation | `ai_ml_governance`, `business_logic` |
| ASI10:2026 | Rogue Agents | `agentic_system_security`, `ai_ml_governance` |

## Spawn rules

- Load this map when the tree has tool/function calling, MCP, LangGraph/Crew/AutoGen, or an agent loop — not for a single-turn chat wrapper with no tools
- ASI02: start with **read-only** tool calls; do not prove missing confirmation by deleting production data
- ASI05: code-interpreter / `eval` / shell tools are in scope even when sandboxed — record the sandbox boundary
- ASI10: test kill switches, max-turn/budget stops, and whether the agent can disable its own policy. A sci-fi write-up without a reachable control is not a finding
- When filing: `OWASP ASI02:2026 — CWE-862 — <one-line issue>`
