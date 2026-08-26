---
name: variant_analysis
description: After one confirmed vulnerability, hunt equivalent source-sink variants across the rest of the codebase and other transports
---

# Variant Analysis

When a vulnerability is confirmed, stop treating it as a singleton. The same root cause almost always exists on sibling endpoints, other languages in a monorepo, jobs/webhooks, or a second framework copy of the same helper. Hunt those cousins before filing and before `finish_scan`.

Load this after the first validated finding in a class (IDOR, SQLi, SSRF, path traversal, mass assignment, insecure default, CI injection).

## When to use

- You have a working PoC (not just a static hit)
- The sink is a shared helper, ORM call, or copy-pasted controller
- The repo is a monorepo or has web + mobile + worker + admin

## Do not use

- Before anything is dynamically validated (that is SAST noise)
- To mass-file scanner duplicates of the same sink
- As a substitute for `exploitability_triage`

## Workflow

1. **Characterize**
   - Source: parameter, header, file, webhook field, agent/MCP input
   - Propagation: concat, deserializer, template, ORM
   - Sink: SQL, exec, request, authorize, render, deserialize, Actions `run:`
   - Missing control: no ownership check, no allowlist, no HMAC, fail-open default

2. **Pattern**
   - Write 3–8 grep/`sg`/semgrep patterns from the real code, not from CWE names
   - Include the helper name (`load_user_file`, `fetch_url`, `whereRaw`) and the anti-pattern (`$request->all()`, `os.getenv(..., "secret")`)

3. **Sweep**
   - Same language first, then other workspaces
   - Other transports: GraphQL, WS, CLI, cron, queue, GitHub Action
   - History only if the live path still ships the pattern

4. **Validate each candidate**
   - Same standard as the original: reachable + user-controlled + sink impact
   - Different object type or tenant is a **new** report; the same sink behind two URLs is **one** report with extra evidence

5. **Stop**
   - When a full sweep of the characterized pattern is done, not when you are bored
   - Note residual candidates you could not reach (auth-gated admin) in the coverage checklist, do not silently drop them

## Pattern examples (illustrative)

| Original finding | Cousin search |
|---|---|
| IDOR on `GET /orders/{id}` | Other `{id}` / `{uuid}` show/update/delete; GraphQL `order(id:)`; jobs that load by id |
| SSRF in link-preview | `webhook`, `avatar`, `import`, `pdf`, `og:` fetchers; worker URL fields |
| `whereRaw` concat | `orderByRaw`, `selectRaw`, `DB::raw`, sibling search endpoints |
| Actions `${{ github.event.issue.title }}` in `run:` | Other `run:` / `env:` intermediaries; `pull_request_target`; agent prompts |
| JWT fallback secret | Other `getenv`/`||` secrets; Docker ENV; Helm values |

## Quality gate

- Each extra variant has its own evidence **or** is attached to the original as "also reachable at …" with one PoC
- Do not clone the original write-up ten times with a different path
- If the helper is fixed in one place but wrappers still concat — that is still in scope

## Pair with

The vuln-class skill that produced the original finding, plus `source_aware_sast` for the sweep and `exploitability_triage` before filing.
