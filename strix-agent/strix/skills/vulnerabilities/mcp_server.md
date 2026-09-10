---
name: mcp_server
description: White-box and live testing of MCP server implementations — transports, tools/call auth, schema enforcement, destructive tools, TLS to backends, and tool-result injection
---

# MCP Server Implementation

Use this when the target **is** an MCP server (tool registry, `tools/call` / `tools/list` handlers, FastMCP, Streamable HTTP, SSE, stdio, WebSocket), not when it only ships a client config for Claude/Cursor. Pair with `agentic_system_security` for confused-deputy chains and `llm_prompt_injection` for tool-result injection.

Checked-in `CLAUDE.md` / `.cursor/mcp.json` is `agent_mcp_config`. This skill is the server-side counterpart.

## Attack surface

```text
MCP client / LLM
  -> transport (stdio | Streamable HTTP | SSE | TCP | WebSocket)
  -> initialize / tools/list / tools/call / resources/*  (auth? session? capability?)
  -> tool registry / base Tool.execute
  -> input schema (declared vs actually validated)
  -> handler (read / write / delete)
  -> downstream HTTP client (TLS verify? URL built from IDs?)
  -> tool result string returned into the model context
```

## Reconnaissance

```bash
rg -n -g '!node_modules' -g '!.git' \
  'tools/call|tools/list|FastMCP|mcp\.server|modelcontextprotocol|ToolRegistry|StatelessHandler|StreamableHTTP'
rg -n 'ssl\s*=\s*False|verify\s*=\s*False|CERT_NONE|insecure_skip_verify'
rg -n '0\.0\.0\.0'
rg -n 'delete_|confirm\s*=' --glob '*tool*'
```

On a live URL, send JSON-RPC (not only REST GET). A `401` on `/login` does not mean the MCP transport was tested:

```bash
curl -sS -D - -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"strix","version":"0"}}}' \
  "$TARGET_URL"
curl -sS -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}' \
  "$TARGET_URL"
```

Record status, body, and whether `tools/call` is accepted without a session, token, or `initialize`.

## What to prove

### Unauthenticated or sessionless `tools/call` (MCP07 / API2)

- Stateless handlers that skip `initialize` and pass `params` straight to `call_tool`
- HTTP/SSE listeners with no bearer/gateway check (or a removed gateway)
- `tools/list` vs `tools/call` authorization mismatch (listing is not calling)

File when an unauthenticated caller can invoke a tool. Do not file "FastAdmin is off" as a substitute for testing the MCP handler.

### TLS verification disabled to the backend (MCP07 / A02)

- `ssl=False`, `TCPConnector(ssl=False)`, `verify=False`, `ssl.CERT_NONE`, `insecure_skip_verify`
- Docstrings or env names (`VERIFY_SSL`) that are never read

This is reportable from source with the exact assignment; live MITM is optional confirmation.

### Declared schema not enforced (MCP07)

- Base `execute()` / `call_tool()` forwards the raw `arguments` dict
- Individual tools optionally `model_validate()`; read/delete tools skip it
- JSON Schema on `tools/list` is documentation, not a gate

### Path / endpoint manipulation via raw IDs (MCP07 / API1)

- `arguments["*_id"]` interpolated into URLs (`f".../{id}"`)
- Non-integer IDs such as path segments that change which API object is hit
- Fix evidence: show the client builder uses the unsanitized value

### Destructive tools without confirmation (MCP02 / LLM03)

- Delete / membership / parent-reassign tools with no `confirm` flag, approval, or dry-run
- Annotations such as `destructiveHint` that are not enforced

### Tool results over-share or inject (MCP10 / MCP06 / API3)

- Emails, logins, admin flags, comments, descriptions concatenated into markdown for the model
- Untrusted work-package / news / comment text returned without fencing or sanitization

### Audit and bind address (MCP08 / MCP01)

- Logs that write raw params (API keys, PII)
- Unbounded in-memory audit buffers
- HTTP listener default `0.0.0.0`

## Live testing

1. `initialize` with and without `clientInfo` / `_meta`
2. `tools/list` unauthenticated
3. `tools/call` on a **read** tool first (never start with delete)
4. Invalid types vs declared schema (string where integer is declared)
5. Only then consider a non-destructive write in an authorized test environment

Do not call production delete/update tools to "prove" missing confirmation.

## Validation

- Cite file:line for hardcoded `ssl=False` / missing `model_validate` / raw ID interpolation
- For live auth gaps: request + response of `tools/list` or a read-only `tools/call`
- Do not report "the downstream REST API returned 401" as an MCP-server finding
- Tag `OWASP MCP0x:2025` when that standards map is loaded
