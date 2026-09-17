<p align="center">
  
  <img src="https://github.com/usestrix/.github/raw/main/imgs/cover.png" alt="Strix Banner" width="100%">
  
</p>

<div align="center">

# Strix

### The open-source AI pentesting tool. Autonomous AI hackers that find and fix your app’s vulnerabilities.

<br/>

</div>


>
> Strix integrates with GitHub Actions and CI/CD pipelines so you can run security scans on pull requests and gate releases on the findings you choose - see [CI/CD (GitHub Actions)](#cicd-github-actions) below, or run the full dashboard yourself with [`docker compose up --build`](#-developer-environment-setup) for scheduled/managed scanning.

---


## Strix Overview

Strix are autonomous AI penetration testing agents that act just like real hackers - they run your code dynamically, find vulnerabilities, and validate them through actual proofs-of-concept. Built for developers and security teams who need fast, accurate security testing without the overhead of manual pentesting or the false positives of static analysis tools.

**Key Capabilities:**

- **Full pentesting toolkit** - reconnaissance, exploitation, and validation out of the box
- **Multi-agent orchestration** - teams of AI pentesters that collaborate and scale
- **Exploit validation where confirmed** - PoCs and reproduction steps when the agent can validate a finding, with reports preserving scan context
- **Developer‑first CLI** - actionable findings with remediation guidance
- **Fix guidance & reporting** - remediation steps, agent-assisted patch workflows, and pentest reports


<br>


<div align="center">
  <img src=".github/screenshot.png" alt="Strix Demo" width="1000" style="border-radius: 16px;">
</div>


## Use Cases

- **Application Security Testing** - Detect and validate critical vulnerabilities in your applications
- **Rapid Penetration Testing** - Get penetration tests done in hours, not weeks, with compliance reports
- **Bug Bounty Automation** - Automate bug bounty research and generate PoCs for faster reporting
- **CI/CD Integration** - Run scans in CI/CD and decide which severities or policies block promotion

## 🚀 Quick Start

**Prerequisites:**
- Docker (running)
- An LLM API key from any [supported provider](docs/llm-providers/overview.mdx) (OpenAI, Anthropic, Google, etc.)

### Installation & First Scan

```bash
# Install Strix (this fork, not the upstream package)
pip install "strix-agent @ git+https://github.com/maruthis/strix"

# Configure your AI provider
export STRIX_LLM="openai/gpt-5.4"
export LLM_API_KEY="your-api-key"

# Run your first security assessment
strix --target ./app-directory
```

> [!NOTE]
> First run automatically pulls the sandbox Docker image. Results are saved to `strix_runs/<run-name>`

### Or: run the full SaaS dashboard

Want the multi-tenant dashboard (org accounts, connected repos/domains,
scheduled scans, PR reviews, Chat) instead of the bare CLI? The backend
(this repo, `saas/backend/`) and the frontend now live in **separate
repos** — check out [`strixui`](https://github.com/maruthis/strixui) as a
sibling directory next to this one, then bring the whole stack up (backend
+ frontend + a gateway serving both from one origin) with:

```bash
docker compose up --build
```

Open **http://localhost:8095** — frontend at `/`, API at `/api/*`. It runs
against the mock scanner by default (no Docker socket access needed inside
the container, no LLM key needed to explore the UI); set
`SAAS_ENABLE_REAL_SCAN=1` (already wired up in the provided
`docker-compose.yml`) once you want genuine scans through this same
engine — that mode also needs the host's Docker socket mounted in, since
each scan spins up its own sandbox container. See
[Developer Environment Setup](#-developer-environment-setup) below for the
full picture, or [`saas/README.md`](saas/README.md) directly.

---

## ☁️ Strix Platform

This repo includes the full-stack penetration testing platform's source under
[`saas/`](saas/) — a multi-tenant dashboard you self-host rather than a
service this fork operates. Deploy it wherever you like (e.g.
`<servername>.strix.ai`, or any domain/subdomain you control), sign in,
connect your repos and domains, and launch a pentest in minutes.

- **Validated findings with PoCs where available** - findings include reproduction context and proof material when validation succeeds
- **Agent-assisted fixes** - remediation guidance and patch-generation workflows that still require code review
- **Scheduled pentesting** - recurring scans through the self-hosted dashboard, backed by the same engine
- **DevSecOps integrations** - GitHub/GitLab repository access, PR-review hooks, CI/CD usage, outbound webhooks, and billing hooks
- **Org-aware context** - knowledge base entries, previous findings, and repo/domain metadata inform future work

**[Run it locally with `docker compose up --build` →](#-developer-environment-setup)** or see [`saas/README.md`](saas/README.md) for deploying your own instance.

---

## 🤖 Use Strix from Your Coding Agent

Strix is agent-ready. Give Claude Code, Cursor, Codex, or any [SKILL.md-compatible](https://agentskills.io) agent the ability to run pentests, fix findings, and set up CI scanning:

```bash
npx skills add maruthis/strix
```

This installs eight skills: **penetration-testing-with-strix** (run headless scans and read results), **fix-security-vulnerabilities-with-strix** (remediate + re-scan to verify), **ci-security-scanning-with-strix** (PR scanning in CI), plus target-specific workflows: **application-security-testing**, **web-app-penetration-testing**, **api-security-testing**, **owasp-top-10-testing**, and **find-security-vulnerabilities-in-code**. All of them install and run this fork (`pip install "strix-agent @ git+https://github.com/maruthis/strix"`), not the upstream package, so agents get this fork's changes — see [`docs/extending-without-code-changes.md`](docs/extending-without-code-changes.md). Read [`AGENTS.md`](AGENTS.md) for a quick reference.

---

## ✨ Features

### Agentic Pentesting Tools

Strix agents come equipped with a comprehensive offensive security toolkit - the same tools used by professional penetration testers and ethical hackers:

- **HTTP Interception Proxy** - Full request/response manipulation and analysis with Caido
- **Browser Exploitation** - Automated browser for testing XSS, CSRF, clickjacking, and auth bypass flows
- **Shell & Command Execution** - Interactive terminal for exploit development and post-exploitation
- **Custom Exploit Runtime** - Python sandbox for writing and validating proof-of-concept exploits
- **Reconnaissance & OSINT** - Automated attack surface mapping, subdomain enumeration, and fingerprinting
- **Static & Dynamic Code Analysis** - SAST + DAST capabilities for comprehensive application security testing
- **Vulnerability Knowledge Base** - Structured findings with CVSS scoring and OWASP classification

### Comprehensive Vulnerability Scanner

Strix identifies, validates, and exploits a wide range of security vulnerabilities across the OWASP Top 10 and beyond:

- **Broken Access Control** - IDOR, privilege escalation, auth bypass
- **Injection Attacks** - SQL injection, NoSQL injection, OS command injection, SSTI
- **Server-Side Vulnerabilities** - SSRF, XXE, insecure deserialization, RCE
- **Client-Side Attacks** - XSS (stored/reflected/DOM), prototype pollution, CSRF
- **Business Logic Flaws** - Race conditions, payment manipulation, workflow bypass
- **Authentication & Session** - JWT attacks, session fixation, credential stuffing vectors
- **Infrastructure & Cloud** - Misconfigurations, exposed services, cloud security issues
- **API Security** - Broken authentication, mass assignment, rate limiting bypass

### Graph of Agents (Multi-Agent Pentesting)

Advanced multi-agent orchestration for comprehensive automated penetration testing:

- **Distributed Pentesting** - Specialized AI agents for recon, exploitation, and post-exploitation
- **Scalable Security Testing** - Parallel execution across multiple targets for fast, comprehensive coverage
- **Dynamic Coordination** - Agents share discoveries, chain vulnerabilities, and collaborate like a red team

---

## 🖥️ Local Web Viewer

Every scan writes its results to disk as it runs. Bring them up in a local dashboard with a single command:

```bash
# Open the most recent run
strix view

# ...or open a specific run by name
strix view my-run-name

# Expose the viewer on all IPv4 interfaces at a fixed port
strix view --host 0.0.0.0 --port 8080 --no-open
```

`strix view` starts a lightweight local server (bound to `127.0.0.1` on a random port) and opens your browser to a private, tokened link. Nothing leaves your machine: the dashboard reads the run's files straight off disk, with no cloud account or upload required. The UI ships prebuilt with Strix, so there is no extra install and no JS build step.

Use `--host 0.0.0.0` to make the viewer reachable from other machines. Replace `0.0.0.0` in the printed URL with the server's reachable IP or hostname. The token in that URL grants access to the selected run's scan data, history, and steering, so only share it with trusted users and restrict the port with your firewall. Requests without the token-derived session cannot read run data.

### What's in the dashboard

- **Overview**: run status, target, and a severity breakdown of everything found so far.
- **Vulnerabilities**: each finding with its severity, details, validation context, and reproduction steps where available.
- **Agent graph**: a live map of the multi-agent team, showing which agent is doing what.
- **Steering**: send instructions to a live scan from the browser to redirect the agents mid-run.
- **History**: browse past runs on this machine and jump between them.
- **Reports**: generate a shareable report and email it to yourself or your team.

---

## Usage Examples

### Basic Usage

```bash
# Scan a local codebase
strix --target ./app-directory

# Security review of a GitHub repository
strix --target https://github.com/org/repo

# Black-box web application assessment
strix --target https://your-app.com
```

### API Testing (OpenAPI / Swagger / Postman)

Point Strix at an API contract and it tests every declared endpoint instead of
having to discover them by crawling. Pair the spec with the live base URL so the
agent knows where to send traffic:

```bash
# OpenAPI / Swagger file (.json / .yaml)
strix --target ./openapi.yaml --target https://api.your-app.com

# Postman collection export
strix --target ./collection.postman_collection.json --target https://api.your-app.com

# Postman collection pulled live by id (no manual export)
export POSTMAN_API_KEY="PMAK-..."
strix --target postman://<collection-uuid>

# ...with a Postman environment to resolve {{baseUrl}} / token variables
strix --target "postman://<collection-uuid>?env=<environment-uuid>"
```


### Advanced Testing Scenarios

```bash
# Grey-box authenticated testing
strix --target https://your-app.com --instruction "Perform authenticated testing using credentials: user:pass"

# Multi-target testing (source code + deployed app)
strix -t https://github.com/org/app -t https://your-app.com

# Targets from a file, one target per non-empty, non-comment line
strix --target-list ./targets.txt

# White-box source-aware scan (local repository)
strix --target ./app-directory --scan-mode standard

# Focused testing with custom instructions
strix --target api.your-app.com --instruction "Focus on business logic flaws and IDOR vulnerabilities"

# Provide detailed instructions through file (e.g., rules of engagement, scope, exclusions)
strix --target api.your-app.com --instruction-file ./instruction.md

# Force PR diff-scope against a specific base branch
strix -n --target ./ --scan-mode quick --scope-mode diff --diff-base origin/main
```

### Headless Mode

Run Strix programmatically without interactive UI using the `-n/--non-interactive` flag - perfect for servers and automated jobs. The CLI prints real-time vulnerability findings and the final report before exiting. Exits with non-zero code when vulnerabilities are found.

```bash
strix -n --target https://your-app.com
```

### CI/CD (GitHub Actions)

Strix can be added to your pipeline to run a security test on pull requests with a lightweight GitHub Actions workflow:

```yaml
name: strix-penetration-test

on:
  pull_request:

jobs:
  security-scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
        with:
          fetch-depth: 0

      - name: Install Strix
        run: pip install "strix-agent @ git+https://github.com/maruthis/strix"

      - name: Run Strix
        env:
          STRIX_LLM: ${{ secrets.STRIX_LLM }}
          LLM_API_KEY: ${{ secrets.LLM_API_KEY }}

        run: strix -n -t ./ --scan-mode quick
```

> [!TIP]
> In CI pull request runs, Strix automatically scopes quick reviews to changed files.
> If diff-scope cannot resolve, ensure checkout uses full history (`fetch-depth: 0`) or pass
> `--diff-base` explicitly.

### Configuration

```bash
export STRIX_LLM="openai/gpt-5.4"
export LLM_API_KEY="your-api-key"

# Optional
export LLM_API_BASE="your-api-base-url"  # if using a local model, e.g. Ollama, LMStudio
export PERPLEXITY_API_KEY="your-api-key"  # for search capabilities
export STRIX_REASONING_EFFORT="high"  # control thinking effort (default: high, quick scan: medium)
```

> [!NOTE]
> Strix automatically saves your configuration to `~/.strix/cli-config.json`, so you don't have to re-enter it on every run.

#### Sign in with a ChatGPT subscription

Instead of a metered API key, you can run Strix on your ChatGPT Plus/Pro subscription:

```bash
strix auth login chatgpt      # sign in with your ChatGPT account

export STRIX_LLM="chatgpt/gpt-5.4"   # chatgpt/<model> runs on the subscription
strix --target ./app-directory

strix auth status             # show the active sign-in
strix auth logout             # forget the sign-in
```

#### Connect your own MCP servers

Strix can connect to Model Context Protocol (MCP) servers you list and expose their tools to the agent during a run. Create `~/.strix/mcp-servers.json` with a JSON list of servers. Each entry is either a local `stdio` server that Strix launches as a subprocess, or a remote `http` server:

```json
[
  {
    "name": "local_fs",
    "transport": "stdio",
    "command": "npx",
    "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path/to/project"]
  },
  {
    "name": "github",
    "transport": "http",
    "url": "https://api.githubcopilot.com/mcp/",
    "auth": { "kind": "bearer", "token": "your-token" },
    "allowed_tools": ["list_issues"]
  }
]
```

Each server's tools are namespaced by `name` (for example `local_fs_read_file`). Omit `allowed_tools` to expose every tool the server offers, or set it to a list to restrict which tools the agent can call. The file is optional, and a server that fails to connect is skipped without failing the run. You can point Strix at a different file with `STRIX_MCP_CONFIG`.

**Recommended models for best results:**

- [OpenAI GPT-5.4](https://openai.com/api/) - `openai/gpt-5.4`
- [Anthropic Claude Sonnet 4.6](https://claude.com/platform/api) - `anthropic/claude-sonnet-4-6`
- [Google Gemini 3 Pro Preview](https://cloud.google.com/vertex-ai) - `vertex_ai/gemini-3-pro-preview`

See the [LLM Providers documentation](docs/llm-providers/overview.mdx) for all supported providers including Vertex AI, Bedrock, Azure, and local models.

## Enterprise Pentesting

`saas/` is already built for this: multi-tenant orgs with role-based
access, custom compliance-ready penetration testing reports, GitHub/GitLab
integrations, BYOK model support (per-org LLM settings), and self-hosted
deployment by construction (there's no hosted version to opt out of). See
[`docs/saas-architecture.md`](docs/saas-architecture.md) for how it's put
together, and [`saas/README.md`](saas/README.md) to deploy your own
instance (e.g. at `<servername>.strix.ai`) with SSO/VPC controls layered
on however your infrastructure normally handles that.

## Documentation

Full documentation is available under [`docs/`](docs/) in this repository
— including detailed guides for usage, CI/CD integrations, skills, and
advanced configuration. Start at [`docs/README.md`](docs/README.md) or
[`docs/quickstart.mdx`](docs/quickstart.mdx).

## 🛠️ Developer Environment Setup

Two things live in this repo — the `strix` engine (Python CLI/library) and
`saas/` (the multi-tenant dashboard built on top of it) — each with its
own setup.

### Engine (`strix/`)

```bash
git clone https://github.com/maruthis/strix.git
cd strix

make dev-install     # uv sync + dev dependencies
make check-all        # ruff format/lint, mypy, pyright, bandit
uv run pytest          # run the test suite
uv run strix --target ./some-project   # run from source
```

Requires Python 3.12+ and [`uv`](https://docs.astral.sh/uv/). `make
setup-dev` also installs the pre-commit hooks. See
[`AGENTS.md`](AGENTS.md)'s "Contributing to this repo" section and
[`CONTRIBUTING.md`](CONTRIBUTING.md) for the full guide, and
[`docs/strix-engine-architecture.md`](docs/strix-engine-architecture.md)
for how the engine itself is structured.

### SaaS dashboard (backend here, frontend in `strixui`)

The frontend has moved out of this repo into its own sibling repo,
[`strixui`](https://github.com/maruthis/strixui) — this repo now holds only
the backend (`saas/backend/`) plus the `strix` engine it calls into. Check
out `strixui` next to this repo (`docker-compose.yml` at the repo root
assumes that layout), then bring the whole stack up together:

```bash
docker compose up --build
```

What it does (see the compose file's own comments for the full detail):

- Builds and starts three containers behind one gateway on
  `http://localhost:8095`: the FastAPI **backend**, the **frontend** (built
  from `../strixui`), and an nginx **gateway** that serves both from a
  single origin (frontend at `/`, API at `/api/*` — deliberately *not* two
  separate host ports, since some browsers/privacy extensions treat
  different `localhost` ports as separate tracking contexts and drop the
  session cookie between them).
- Runs against the built-in mock scanner by default. Set
  `SAAS_ENABLE_REAL_SCAN=1` (already set in the provided
  `docker-compose.yml`, along with `STRIX_LLM`/`LLM_API_KEY` — populate
  those with a real key to run genuine scans through this same engine
  instead of canned findings) — real-scan mode also needs the host's
  Docker socket mounted into the backend container, since each scan spins
  up its own sandbox container as a sibling of the backend one.

For running the backend on its own (e.g. against the CLI-style workflow, or
while iterating on `strixui` separately with its own dev server), see
[`saas/README.md`](saas/README.md) and [`saas/CONFIG.md`](saas/CONFIG.md)
for prerequisites, environment variables, and the backend test suite.
[`docs/saas-architecture.md`](docs/saas-architecture.md) covers how the
backend, frontend, and data model fit together — note it still describes
the pre-split, single-repo `saas/frontend/` layout in places, so prefer
`docker-compose.yml` as the source of truth for how the two repos actually
wire together today.
