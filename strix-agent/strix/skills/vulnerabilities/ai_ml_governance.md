---
name: ai_ml_governance
description: Testable AI/ML governance — model identity pinning, provider data retention, prompt/PII telemetry, guardrails that fail closed, and training/RAG data controls. Not policy paperwork.
---

# AI / ML Governance (testable)

Use this when the target sends data to a model provider, hosts a model, retrieves embeddings, logs prompts, or claims safety/guardrails. Pair with `llm_applications` (OWASP LLM01–LLM10 architecture) and `information_disclosure` for concrete leaks.

This skill is **not** an ISO 42001/NIST AI RMF audit of the organization. Do not invent findings from missing ethics-board minutes, model-card PDFs, or vendor DPAs you cannot observe. Only report controls that are missing, fail-open, or contradicted **in the running system or source**.

## What “governance” means here

| Topic | Testable question | Not a finding |
|---|---|---|
| Model governance | Is the deployed model identity pinned and auditable? | “No model card in Confluence” |
| AI governance | Do high-impact actions require a deterministic gate (authz, confirm, allowlist)? | “No AI steering committee” |
| Data governance | Does tenant/ACL/retention survive chunking, logs, and the provider call? | “No data-classification policy PDF” |
| Guardrails | Is there an enforceable filter **outside** the prompt, and does it fail closed? | “The system prompt says be helpful and safe” |
| Sensitive data in transit | What exact fields leave the trust boundary to a provider, log sink, or eval store? | Speculative “the LLM might memorize this” |

## Reconnaissance

```bash
rg -n -g '!node_modules' -g '!.git' \
  'openai|anthropic|litellm|langchain|llama_index|bedrock|vertexai|ChatOpenAI|AzureOpenAI'
rg -n 'store\s*=\s*True|logprobs|prompt_log|messages\s*=|system_prompt|moderation'
rg -n 'temperature|gpt-4|claude-|latest|huggingface.co/.+/.+:'
rg -n 'chromadb|pinecone|weaviate|faiss|embeddings'
```

Inventory, for each model call:

1. Provider, model id, whether the id is a mutable alias (`latest`, unpinned HF tag)
2. Request payload: system prompt, user content, tools, RAG chunks, memory
3. Provider options: retention/`store`, training opt-out, region, logging
4. App logs/traces: full prompt, completions, tool args
5. Guardrail: moderation API, output schema, allowlist, or prompt-only
6. Downstream: training/eval/feedback jobs, vector index, human review queue

## Model governance

- Floating model aliases (`gpt-4`, `claude-3-opus-latest`, `:latest` image/weights) with no digest/revision recorded at call time
- System prompts or tool schemas that contain API keys, connection strings, or internal URLs (LLM08 path)
- No correlation id that ties a completion to model id, prompt revision, and tenant — you cannot reconstruct “which model decided this”
- Custom weights / pickle / `trust_remote_code=True` / runtime `from_pretrained` without a pin (LLM04)

File when you can show the **identity actually loaded** is mutable or secret-bearing. “They should pin models” without a mutable alias in source is not enough.

## Sensitive data transmitted to providers

Trace one user-originated record (email, document, ticket, health/financial field) to the HTTPS body of the provider call.

Report when:

- Raw PII, secrets, or another tenant’s RAG chunk is included in `messages` / embeddings with no redaction
- Provider persistence is on (`store=True`, prompt-logging webhooks, “improve the model” flags defaulting to opt-in)
- Debug middleware logs full prompts/completions (APM, stdout, OpenTelemetry attributes)
- Eval/fine-tune exporters copy production chats to a shared bucket or third-party eval SaaS

A chat UI that **displays** the user’s own text is not LLM02. Unauthorized **egress** (other users, operators, providers, logs) is.

Live check: intercept one authenticated request (proxy) and list fields in the provider payload. Whitebox: cite the builder that concatenates user records into the prompt.

## Guardrails

Prompt text is not a guardrail. Test the **enforcement point**:

| Pattern | How to test |
|---|---|
| “You must not reveal secrets” in the system prompt only | Ask for the secret via indirect/tool-result injection; if it returns, the control is LLM01/LLM08, not a passed guardrail |
| Provider moderation / content filter | Send a benign control and a blocked class; then retry with encoding/split. Fail-open on moderation timeout is a finding |
| Output schema / allowlisted tools | Call a disallowed tool or extra field; schema that is advertised on `tools/list` but not validated is the MCP/LLM03 cousin |
| Human confirm for destructive tools | Missing `confirm` / approval binding — see `mcp_server` / ASI02. Do not delete production data to prove it |

Guardrails that **error open** (catch Exception: continue) are findings. Guardrails that only apply in production via an env flag left off in the scanned config are findings if that config is what ships.

## Data governance (RAG, memory, training)

- Ingestion vs retrieval ACL: can tenant B’s document appear in tenant A’s context (LLM09)
- Deletes/ACL changes that do not rebuild or filter embeddings
- Memory stores shared across users/sessions
- User feedback or thumbs-down piped into the next fine-tune without review
- Datasets, fixtures, or notebooks in the repo that contain production-like PII

## NIST AI RMF / ISO 42001 (technical overlay only)

If the scan loaded a NIST/ISO overlay, map evidence to these **engineering** families — do not fail the product for missing paperwork:

| Family | Test in code/runtime |
|---|---|
| Map / inventory | Model, prompt, tool, and corpus identity recorded at inference |
| Measure | Eval/red-team jobs exist for the **deployed** model id, not a different one |
| Manage | Kill switch, max turns/budget, revocation of tool credentials |
| Data | Retention, redaction, tenant filters on the retrieval and log path |
| Transparency | Users can see that a model acted; operators can see which model |

ISO 42001 A.6/A.8 and NIST AI RMF MEASURE/MANAGE overlap these rows. Skip GOVERN process clauses.

## Validation

- Cite file:line or a captured provider request. Model narration is not evidence.
- Distinguish authorized use of the caller’s own data from unauthorized disclosure.
- Tag `OWASP LLM02:2026` / `OWASP ASI09:2026` when those maps are loaded.
- Do not report “no AI governance program” as a vulnerability.
