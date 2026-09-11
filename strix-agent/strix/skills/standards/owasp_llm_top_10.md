---
name: owasp_llm_top_10
description: OWASP Top 10 for LLM Applications 2026 coverage map — spawn specialists for every LLM01-LLM10 row that has surface
---

# OWASP LLM Top 10:2026

Coverage index for applications that call a model, retrieve embeddings, or send user content to a provider. Spawn a specialist for **every** row that applies. Tag findings `OWASP LLM0x:2026` plus CWE.

Load `llm_applications` as the architecture playbook. This map is the **mandatory spawn table** so a chat/RAG/agent feature cannot be closed after only a secrets pass.

**Out of scope:** model-quality evals with no security boundary, ethics-board process, and provider ToS reviews you cannot observe from the target.

## Mandatory coverage

| ID | Category | Spawn with skills |
|---|---|---|
| LLM01:2026 | Prompt Injection | `llm_prompt_injection` |
| LLM02:2026 | Sensitive Information Disclosure | `ai_ml_governance`, `information_disclosure` |
| LLM03:2026 | Excessive Agency | `agentic_system_security`, `broken_function_level_authorization` |
| LLM04:2026 | Supply Chain | `dependency_cve_scanning`, `ai_ml_governance` |
| LLM05:2026 | Data and Model Poisoning | `llm_applications`, `ai_ml_governance` |
| LLM06:2026 | Unbounded Consumption | `unrestricted_resource_consumption` |
| LLM07:2026 | Misinformation | `llm_applications`, `business_logic` |
| LLM08:2026 | Hidden Context Exposure | `llm_prompt_injection`, `information_disclosure` |
| LLM09:2026 | Vector and Embedding Weaknesses | `idor`, `information_disclosure`, `llm_applications` |
| LLM10:2026 | Improper Output Handling | sink skill (`xss`, `sql_injection`, `ssrf`, `rce`, …) plus `llm_applications` |

## Spawn rules

- If the tree calls OpenAI/Anthropic/LiteLLM/LangChain/Bedrock/Vertex or stores embeddings, **every row with surface is mandatory** — do not skip LLM02/LLM04 because recon ranked injection higher. `finish_scan` requires white-box `llm_prompt_injection`, `llm_applications`, and `ai_ml_governance` children (`review_mode='whitebox'`)
- LLM02 includes **data in transit to the provider** (prompts, tools, logs, `store=True`, training opt-in), not only the chat UI leaking another user's thread
- LLM03: if there are no tools/MCP/function-calls, record that and skip the agency specialist; do not skip LLM02
- Pair with `standards/owasp_agentic_top_10` when the app can select tools or delegate to other agents
- When filing: `OWASP LLM02:2026 — CWE-359 — <one-line issue>`
