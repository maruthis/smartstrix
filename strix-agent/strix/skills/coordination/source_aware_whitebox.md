---
name: source-aware-whitebox
description: Coordination playbook for source-aware white-box testing with static triage and dynamic validation
---

# Source-Aware White-Box Coordination

Use this coordination playbook when repository source code is available.

## Objective

Increase white-box coverage by combining source-aware triage with dynamic validation. Source-aware tooling is expected by default when source is available.

## Recommended Workflow

1. Build a quick source map before deep exploitation, including at least one AST-structural pass (`sg` or `tree-sitter`) scoped to relevant paths.
   - For `sg` baseline, derive `sg-targets.txt` from `semgrep.json` scope first (`paths.scanned`, fallback to unique `results[].path`) and run `xargs ... sg run` on that list.
   - Only fall back to path heuristics when semgrep scope is unavailable.
2. Run first-pass static triage to rank high-risk paths.
3. Use triage outputs to prioritize dynamic PoC validation.
4. Keep findings evidence-driven: no report without validation.

## Source-Aware Triage Stack

- `semgrep`: fast security-first triage and custom pattern scans
- `ast-grep` (`sg`): structural pattern hunting and targeted repo mapping
- `tree-sitter`: syntax-aware parsing support for symbol and route extraction
- `gitleaks` + `trufflehog`: complementary secret detection (working tree and history coverage)
- `trivy fs`: dependency, misconfiguration, license, and secret checks

Coverage target per repository:
- one `semgrep` pass
- one AST structural pass (`sg` and/or `tree-sitter`)
- one secrets pass (`gitleaks` and/or `trufflehog`)
- one `trivy fs` pass

## Monorepo Coverage

A single `trivy fs`/`semgrep` invocation at the repo root does not reliably walk into every workspace of a monorepo — each workspace has its own lockfile and dependency tree, and a scan scoped to (or defaulting to) one of them silently leaves the rest unaudited. Before considering dependency/SCA coverage complete:

1. **Enumerate every workspace first.** Find every `package.json`/`requirements.txt`/`go.mod`/etc. in the repo (`find . -name package.json -not -path '*/node_modules/*'` or equivalent) and list them explicitly — server, collector/worker, frontend, desktop/Electron, browser extensions, CLI tools, docs sites, etc. are usually separate workspaces with independent dependency sets.
2. **Run the SCA pass per workspace**, not once at the root — `cd` into each and run `trivy fs .` / `npm audit` / `yarn audit` / `pip-audit` there, so each workspace's lockfile is actually read.
3. **Don't stop at the first vulnerable package found in a dependency tree** — the same CVE'd package (e.g. `protobufjs`, `@langchain/core`) is frequently pulled in independently by multiple workspaces via different parent packages; each occurrence is a separate finding location, not a duplicate.

## Secret History Coverage

A secrets pass over the working tree only catches what's checked out *now* — a credential removed in a later commit is still fully recoverable from git history and is exactly as exploitable. Scope secret scanning to history, not just HEAD:

- Run `gitleaks detect` / `trufflehog` in git-history mode (e.g. `gitleaks detect --log-opts="--all"`, `trufflehog git file://. --since-commit=<root>`), not just a filesystem scan of the current checkout.
- If a credential is found, check `git log --all --oneline -- <path>` and `git branch -r --contains <commit>` to establish how many branches/forks still carry it — that scope materially changes the finding's severity and remediation (rotate + purge history vs. just rotate).

## Infrastructure & CI/CD Coverage

These are easy to skip because they're not "application code," but they're a normal part of source review and are usually a handful of files:

- Kubernetes/Helm manifests (`*.yaml` under `k8s/`, `kubernetes/`, `deploy/`, `charts/`) — check `securityContext` (`allowPrivilegeEscalation`, `privileged`, added `capabilities`, `runAsNonRoot`), resource limits, and any inline secrets.
- `Dockerfile`/`docker-compose.yml` — check the running user, exposed ports, `COPY`/`ADD` of secret files, and base image pinning.
- CI/CD workflows (`.github/workflows/`, `.gitlab-ci.yml`, `Jenkinsfile`) — check for mutable action/image tags (`@v2` vs a pinned SHA), `curl | sh`/`curl | bash` patterns, and secrets exposed to untrusted PR triggers (`pull_request_target`, forked-PR workflows). Load `ci_cd_injection` when these files exist, including workflows that invoke Claude/Codex/Gemini.
- Agent / MCP configs (`.claude/`, `.cursor/`, `mcp.json`, `CLAUDE.md`, `AGENTS.md`, `**/SKILL.md`) — untrusted instructions and overprivileged tools; load `agent_mcp_config`.
- Any vendored/forked upstream project's version marker (`package.json` version, a `VERSION` file, a banner string) — cross-reference it against that upstream's published CVEs; a fork that has drifted from upstream security fixes is a real, checkable finding, not a guess.

## Agent Delegation Guidance

- Keep child agents specialized by vulnerability/component as usual.
- For source-heavy subtasks, prefer creating child agents with `source_aware_sast` skill.
- Use source findings to shape payloads and endpoint selection for dynamic testing.

## Validation Guardrails

- Static findings are hypotheses until validated.
- Dynamic exploitation evidence is still required before vulnerability reporting.
- Keep scanner output concise, deduplicated, and mapped to concrete code locations.
