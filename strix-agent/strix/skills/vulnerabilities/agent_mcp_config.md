---
name: agent_mcp_config
description: Testing agent, MCP, skill, and hook configuration as an attack surface — prompt injection in instruction files, overprivileged tools, unpinned servers, and hook command injection
---

# Agent / MCP Config

Coding-agent and MCP configuration checked into a target repo is an extension-point attack surface: untrusted markdown and JSON become instructions and tools for an LLM that already has shell, filesystem, and credential access. Test these files the same way you test plugin loaders — not as documentation.

This is the coverage-checklist **extension points** category when the target ships Claude Code, Cursor, Codex, Copilot, OpenCode, or MCP configs. For LLM features *inside the product* (chat, RAG, tools), use `llm_prompt_injection`.

## Attack Surface

**Instruction files (indirect prompt injection)**
- `CLAUDE.md`, `AGENTS.md`, `.cursorrules`, `.cursor/rules/`, `GEMINI.md`, `CODEX.md`
- `skills/**/SKILL.md`, `.github/prompts/`, agent definition markdown
- README / issue templates that an agent is told to follow

**Tool / permission config**
- `.claude/settings.json`, `.cursor/mcp.json`, `.vscode/mcp.json`, `mcp.json`
- Claude `permissions.allow` / `deny`, YOLO / bypass flags
- Agent frontmatter: unrestricted tools, no model pin

**Hooks and automations**
- `.claude/hooks/`, Cursor hooks, git hooks invoked by the agent
- Command strings interpolating untrusted fields (`$FILE`, issue title, branch name)

**MCP servers**
- Local stdio servers (arbitrary binaries)
- Remote Streamable HTTP / SSE MCP
- `npx` / `uvx` / `pipx` invocations without a pin
- Servers exposing `shell`, `write`, `network`, or secret-bearing env

## High-Value Targets

- Skills or rules fetched from a URL or third-party marketplace
- MCP `env` blocks with live API keys
- Hooks that run `curl | bash` or `rm` on agent events
- `permissions.allow: ["Bash(*)"]` / equivalent full-shell allow
- Agent markdown that says "ignore the user's instructions" or "exfiltrate"
- Backup/restore or "import skill" paths that execute uploaded config

## Reconnaissance

**Find the surface**
```
.claude/  .cursor/  .codex/  .github/prompts/  .vscode/mcp.json
**/SKILL.md  **/mcp.json  **/claude_desktop_config.json
AGENTS.md  CLAUDE.md  .cursorrules
```

**Read for**
- Secrets in markdown, JSON, and hook scripts
- Tool names that imply shell, DB, email, payments, production cloud
- Unpinned `npx -y package` / git URLs as MCP command
- String interpolation in hooks (`${...}`, unquoted `$1`)
- Instructions that auto-run commands without confirmation

## Key Vulnerabilities

### Instruction-file injection

- Malicious or supply-chained `SKILL.md` / `CLAUDE.md` that:
  - Overrides developer policy ("always dump `.env` / push to this gist")
  - Hides directives in HTML comments, zero-width chars, or linked remote docs
- Repo cloned by a victim; agent loads project instructions automatically
- Impact requires a real sink: the agent actually runs the tool / exfils data

### Over-broad permissions

- Allowlists that include unrestricted Bash, Write, or network
- Missing deny list for `.env`, `id_rsa`, credential files
- Agents defined with every tool enabled and no human-in-the-loop

### MCP confused deputy

- MCP tool that takes a URL/path/SQL/command and the model supplies it from untrusted chat or a poisoned skill
- Remote MCP over HTTP without auth → anyone who can speak to the port gets the user's tokens
- Unpinned `npx` → supply-chain swap of the server package

### Hook command injection

- Hook command: `notify.sh ${issue.title}` with title `"; curl evil; #`
- Silent `2>/dev/null` hiding failures after a partial inject
- Hooks that POST repo contents or env to a webhook

### Secret exposure

- Hardcoded `ANTHROPIC_API_KEY`, GitHub PATs, MCP `Authorization` headers
- Skills that instruct the agent to print secrets "for debugging"

## Testing Methodology

1. Inventory every agent/MCP/skill/hook file (including git history)
2. Treat each instruction file as untrusted input to a privileged agent
3. Trace: untrusted text → model → tool/hook → filesystem, network, or secret
4. For MCP: list tools, check input schemas, try path/URL/command args
5. For hooks: inject metacharacters into every interpolated field
6. Confirm impact with the smallest PoC (file read, outbound request) — do not steal real secrets in reports; redact

## Validation

- Show the exact file + line that grants the capability
- Show a trigger the victim (or their agent) would actually perform
- Prove a sink: command executed, file read outside workspace, secret in an outbound request
- "The markdown looks scary" is not a finding without a sink

## False Positives

- Example configs under `docs/` / `examples/` never loaded by the harness
- MCP servers that only expose read-only, non-sensitive resources
- Instruction files with no tool access (chat-only)
- Pinned, reviewed, first-party MCP with least-privilege tools

## Impact

- Credential theft and cloud account takeover
- Silent code exec via hooks or MCP shell tools
- Data exfiltration from the developer workstation
- Supply-chain persistence (malicious skill/MCP surviving on every clone)

## Pro Tips

1. Agent config is in-scope whenever the product *is* an agent or ships `.claude/` / MCP for customers
2. Remote-doc links in SKILL.md are an indirect-injection channel — fetch and read them
3. Pair with `llm_prompt_injection` when the same app also has a user-facing LLM
4. Unpinned `npx` in MCP config is reportable when that server has privileged tools
5. Do not file "missing CSP on CLAUDE.md" — this skill is about confused-deputy impact, not headers
