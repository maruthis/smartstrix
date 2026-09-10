---
name: nist_ai_rmf
description: NIST AI RMF technical overlay — testable Map/Measure/Manage controls for model identity, data egress, guardrails, and agent authority. Policy paperwork is out of scope.
---

# NIST AI RMF (technical overlay)

Coverage index for **testable** NIST AI Risk Management Framework functions (Map, Measure, Manage) as they appear in source and runtime. Spawn specialists for every row with surface. Tag findings `NIST AI RMF <function>` plus CWE.

**Out of scope:** AI ethics boards, impact-assessment templates, vendor DPAs, staff training records, and ISO 42001 Statements of Applicability. Those are organizational audits, not pentest findings.

## Mandatory coverage (testable)

| Function | Intent | Spawn with skills |
|---|---|---|
| MAP 1 / 2 | Inventory models, prompts, tools, corpora actually used | `ai_ml_governance` |
| MAP 4 | Data types leaving the boundary (PII to providers/logs) | `ai_ml_governance`, `information_disclosure` |
| MEASURE 2 | Eval/red-team against the **deployed** model id | `llm_applications` |
| MEASURE 3 | Abuse of tools, injection, excessive agency | `llm_prompt_injection`, `agentic_system_security` |
| MANAGE 1 | Guardrails fail closed; moderation/timeouts not skipped | `ai_ml_governance` |
| MANAGE 2 | Kill switch, max turns/budget, credential revocation | `agentic_system_security`, `unrestricted_resource_consumption` |
| MANAGE 4 | High-impact actions need deterministic authz/confirm | `mcp_server`, `broken_function_level_authorization` |
| GOVERN 1.6* | Transparency of which model acted (logs, not a policy PDF) | `ai_ml_governance` |

\*Only the observability slice — not the organizational GOVERN catalog.

## Spawn rules

- This overlay does **not** replace `owasp_llm_top_10` / `owasp_agentic_top_10`; if both are loaded, merge and spawn each skill at most once
- Skip MEASURE 2 if there is no eval harness in the tree; record that as coverage, do not invent an eval-program finding
- When filing: `NIST AI RMF MAP 4 — CWE-359 — <one-line issue>`
