# Extending security coverage and compliance support without code changes

This document covers two related things: **how Strix can be deployed and
used** (standalone CLI, this repo's saas dashboard, CI/CD, or bolted onto
another coding agent), and **how to add new vulnerability coverage or
compliance-standard support** — by dropping in a markdown file — without
touching Python or TypeScript. It complements
[`strix-engine-architecture.md`](strix-engine-architecture.md) (§2) and
[`saas-architecture.md`](saas-architecture.md) (§6.3), which describe the
mechanism this document is about *using*.

## 0. Ways to run Strix

The same engine (`strix/`) backs every mode below — there is one scan
implementation, invoked five different ways. None of these require
forking or modifying `strix/`.

### 0.1 Standalone CLI + local web viewer

```bash
pip install "strix-agent @ git+https://github.com/maruthis/strix"
export STRIX_LLM="openai/gpt-5.4"
export LLM_API_KEY="your-api-key"
strix --target ./app-directory
```

(Installing from `git+https://github.com/maruthis/strix` rather than the
upstream `strix-agent` PyPI package is what gets this fork's changes —
see §1-§5 below.)

Runs entirely on your machine (Docker sandbox + your own LLM key), no
account or cloud dependency. Results are written to
`strix_runs/<run-name>/` as the scan progresses. `strix view` starts a
local server bound to `127.0.0.1` with a tokened link and opens a
prebuilt dashboard (overview, findings, live agent graph, mid-run
steering, run history, shareable reports) reading straight off disk —
nothing leaves the machine. This is the right mode for local/ad-hoc
testing, air-gapped environments, or anyone who wants to see exactly
what ran.

### 0.2 The saas dashboard (this repo's `saas/`, or the hosted `app.strix.ai`)

The multi-tenant dashboard documented in full in
[`saas-architecture.md`](saas-architecture.md): connect GitHub/GitLab
repos and domains, click "New Pentest" (or let a `PentestSchedule` cron
fire one, or trigger one from a PR, or from Chat), and the backend calls
the same engine (`run_strix_scan`, §6.3 of that doc) inside a job queue,
storing structured `Issue` rows and a downloadable PDF report instead of
a local `strix_runs/` directory. This is the right mode for a team that
wants shared history, role-based access, scheduled recurring scans, and
report distribution rather than everyone running the CLI locally.

### 0.3 CI/CD pipeline

Add a step to any pipeline that can run a shell command and Docker.
GitHub Actions example (from the top-level `README.md`):

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
          fetch-depth: 0   # needed for diff-scope resolution
      - name: Install Strix
        run: pip install "strix-agent @ git+https://github.com/maruthis/strix"
      - name: Run Strix
        env:
          STRIX_LLM: ${{ secrets.STRIX_LLM }}
          LLM_API_KEY: ${{ secrets.LLM_API_KEY }}
        run: strix -n -t ./ --scan-mode quick
```

`-n`/`--non-interactive` (headless mode) prints findings and the final
report to stdout and exits non-zero when vulnerabilities are found —
built for gating a build. In a PR run, Strix automatically scopes a
`quick` scan to changed files (`--scope-mode diff`, resolved against
`--diff-base` or the PR's base branch); this is the same diff-scoping
`resolve_diff_scope_context` that saas's own PR review feature uses
(`saas-architecture.md` §6.5) — CI and saas PR reviews are two callers
of the same scoping logic, not two implementations. Any CI system that
can run a Docker-capable shell step (GitLab CI, Jenkins, CircleCI, Buildkite,
etc.) works the same way; GitHub Actions is just the documented example.

### 0.4 As a skill inside another coding agent (Claude Code, Cursor, Codex, ...)

```bash
npx skills add maruthis/strix
```

This installs eight [SKILL.md-compatible](https://agentskills.io) skills
(`skills/*/SKILL.md` at this repo's root) into whatever coding agent runs
the command, giving that agent the ability to invoke Strix as a tool
rather than a human running it directly:

| Skill | What it lets the coding agent do |
|---|---|
| `penetration-testing-with-strix` | Run a headless scan and read back results |
| `fix-security-vulnerabilities-with-strix` | Remediate a finding and re-scan to verify the fix |
| `ci-security-scanning-with-strix` | Set up PR scanning in CI (i.e., write the §0.3 workflow for you) |
| `application-security-testing` | Whole-product AppSec review: pick the right test per asset, then rank results |
| `web-app-penetration-testing` | Black-box pentest of a live web app or staging site |
| `api-security-testing` | REST/GraphQL/gRPC APIs against the OWASP API Security Top 10 |
| `owasp-top-10-testing` | Systematic OWASP Top 10:2025 assessment with honest per-category coverage |
| `find-security-vulnerabilities-in-code` | White-box review of a repo or working tree |

All of them route to the *local* CLI/Docker path (§0.1) — every install
instruction inside them uses `pip install "strix-agent @
git+https://github.com/maruthis/strix"`, not the upstream PyPI package,
so an agent following them gets this fork's changes (the `--skill` flag,
ref-pinning, etc.), not the vendor's. The upstream `usestrix/strix`
repo also ships a `managed-pentesting-with-strix` skill that drives the
real, vendor-hosted `app.strix.ai` platform — that skill was **deliberately
dropped** from this fork rather than carried over, because its entire
content (API base URL, endpoint shapes, auth) describes infrastructure
this fork doesn't operate; an agent following it from `maruthis/strix`
would have called the vendor's real SaaS with the user's own account,
not anything this fork controls. `saas/` (§0.2) is not exposed as an
agent skill today because it isn't deployed at a public URL other
people's agents could call — see `saas-architecture.md` if that changes.

This is a different "no code change" story from §1-§5 below: it's not
about extending Strix's own coverage, it's about *exposing* Strix to a
codebase and its resident coding agent as a callable capability — one
shell command, no repo changes beyond what `npx skills add` writes (and,
for this fork, the one-time edit of the skill files themselves to point
at `maruthis/strix` instead of `usestrix/strix` — already done). See
[`AGENTS.md`](../AGENTS.md) for the quick reference these skills are
built from.

### 0.5 As a library, from your own automation

Everything above is a thin wrapper over the same Python entry points
(`strix.core.runner`, `strix.core.inputs.build_root_task`). Headless
mode (§0.3) plus the exit-code convention is generally the simplest
integration point for custom automation (a cron job, an internal
tool, a queue worker) that isn't a coding agent and isn't CI — shell out
to `strix -n --target ... --scan-mode quick` and parse the exit code and
JSON report, the same way `saas/backend/app/jobs.py` does when it calls
`run_strix_scan(...)` in-process (`saas-architecture.md` §6.3).

## 1. Adding vulnerability coverage or compliance standards — the short version

| You want to... | strix engine (CLI/SDK) | saas dashboard |
|---|---|---|
| Add a new vulnerability class / testing technique | **No code change** — drop a `.md` file in `strix/skills/vulnerabilities/` | Selectable today only via `Pentest.custom_instructions` (free text); not in the standards picker |
| Add a new compliance standard (e.g. HIPAA, SOC 2, ISO 27001) | **No code change** — drop a `.md` file in `strix/skills/standards/` | Requires a 2-line allowlist edit in `saas/backend/app/standard_skills.py` (§4 below) to appear in the picker |
| Point at a whole separate, private skill library (not even inside `strix/`) | **No code change** — `strix.skills.register_skill_dir(path)` | Not currently wired up; would need one call added at startup |

## 2. How skills work (the mechanism)

A **skill** is a markdown file with YAML frontmatter:

```markdown
---
name: hipaa
description: Testable HIPAA Security Rule technical safeguards (§164.312) — spawn one specialist per safeguard family.
---

## Coverage map

| Safeguard | What to test | Spawn as |
|---|---|---|
| Access control (§164.312(a)(1)) | ... | ... |
```

Skills live under `strix/skills/<category>/<name>.md`. Nothing in the
engine hardcodes the list of skill names — `strix/skills/__init__.py`
discovers every `.md` file under every category directory at call time
(`get_all_skill_names()`, `get_available_skills()`). Adding a file to an
existing category directory is immediately usable — no import, no
registry, no restart-triggering change to any `.py` file. This is why
the platform already ships two skill categories that exist for exactly
this purpose:

- **`strix/skills/standards/`** — compliance/standards coverage maps
  (currently `owasp_top_10`, `owasp_asvs`, `owasp_api_top_10`, `pci_dss`,
  `nist_ssdf`). Each is a lean table mapping the standard's testable
  controls to specialist agents to spawn — not a copy of the standard
  itself.
- **`strix/skills/vulnerabilities/`** — deep-dive technique guides for
  one vulnerability class at a time (currently 25+ files: `sql_injection`,
  `ssrf`, `idor`, `cryptographic_failures`, `session_management`, etc.).

Both are loaded the same way as every other skill category
(`frameworks/`, `technologies/`, `protocols/`, `tooling/`, `cloud/`,
`custom/`) — there is nothing structurally special about "standards" or
"vulnerabilities" beyond convention.

### Using a new skill from the CLI — no code change at all

```bash
strix --target ./my-project --skill hipaa
strix --target ./my-project --skill owasp_top_10 --skill hipaa
```

`--skill` is validated by `validate_requested_skills()`
(`strix/skills/__init__.py`), which checks the file exists and the
request is ≤5 skills — it does not consult any hardcoded list. Drop the
file in, and it is immediately a valid `--skill` argument. The name is
also persisted across `--resume` (`strix/interface/cli_args.py`).

### Using a new skill from a child agent — no code change at all

The root agent (and any specialist it spawns) can request skills by name
when calling `create_agent`, going through the identical
`validate_requested_skills()` check. A new `strix/skills/vulnerabilities/*.md`
file becomes something the root agent can hand to a specialist the moment
it exists — the root agent's own system prompt already lists available
skill categories, so a newly-added file shows up in `get_available_skills()`
without any prompt-template change.

### Using a private skill library outside the repo — no code change,  one function call

```python
from strix.skills import register_skill_dir

register_skill_dir("/path/to/our-internal-skills")
```

Registered directories are searched *before* the packaged `strix/skills/`
tree and can both add new skills and override a built-in one with the
same relative path (`<category>/<name>.md`). This is the escape hatch
for an organization that wants proprietary compliance/testing playbooks
without forking `strix/` at all — e.g. an internal `finra` or `iso27001`
standard, or a company-specific "our auth stack" skill. Nothing in this
repo currently calls `register_skill_dir()` automatically (it's a library
function, not wired to an env var yet) — a small one-time integration
(one call, at process start, reading a directory path from config) is
needed to make it available without touching source at all going forward.

## 3. How this reaches a real scan (`saas/`)

`saas/backend/app/jobs.py` builds `scan_config["skills"]` for every real
pentest via `to_engine_skills()` (`saas/backend/app/standard_skills.py`),
which qualifies the persisted names to `standards/<name>` and passes them
straight through to `strix.core.runner`, which passes them to
`build_root_task` exactly like the CLI's `--skill` flag does
(`strix/core/runner.py:325`). Same mechanism end-to-end — saas is a
caller of the engine, not a separate implementation.

## 4. Why saas needs one small edit for a new *standard*, but not for a new *vulnerability skill*

The saas dashboard's "New Pentest" / "Schedule" modals show a **picker**
of standards to choose from, not a free-text skill list — for a good
reason: an unauthenticated-by-role user shouldn't be able to pass
arbitrary strings into `scan_config["skills"]` (path-like injection into
the engine's skill loader), so `saas/backend/app/standard_skills.py`
validates against an explicit allowlist:

```python
STANDARD_SKILL_NAMES: tuple[str, ...] = (
    "owasp_top_10",
    "owasp_asvs",
    "owasp_api_top_10",
    "pci_dss",
    "nist_ssdf",
)

STANDARD_SKILL_CATALOG: list[dict[str, str]] = [
    {"name": "owasp_top_10", "label": "OWASP Top 10:2025", "description": "..."},
    ...
]
```

`GET /api/pentests/standard-skills` returns `STANDARD_SKILL_CATALOG`
verbatim to populate the picker; `normalize_standard_skills()` rejects
anything not in `STANDARD_SKILL_NAMES` with `400 invalid_skills`.

To add a **new compliance standard** to the saas picker (e.g. HIPAA):

1. Write `strix/skills/standards/hipaa.md` (the actual coverage-map
   content — this part needs no code change, see §1).
2. In `saas/backend/app/standard_skills.py`, add `"hipaa"` to
   `STANDARD_SKILL_NAMES` and one entry to `STANDARD_SKILL_CATALOG`
   (`name`, `label`, `description`).

That's it — no frontend change. `StandardSkillsField`
(`saas/frontend/src/pages/Pentests/PentestsList.tsx`) renders whatever
`GET /api/pentests/standard-skills` returns, so the new option appears
in both the New Pentest and Schedule modals automatically.

To add a **new vulnerability-class skill** (e.g. `graphql_batching_abuse`):

- Write `strix/skills/vulnerabilities/graphql_batching_abuse.md`. It is
  immediately usable via the CLI (`--skill graphql_batching_abuse`) and
  by any agent that requests it internally.
- It is **not** currently exposed as a saas UI checkbox — the "New
  Pentest" picker only lists `standards/`. The saas-side workaround
  today is `Pentest.custom_instructions` (the free-text field on the New
  Pentest modal), which is folded into the engine's
  `scan_config["user_instructions"]` and can ask the root agent to spawn
  a specialist using that skill by name — still no code change, just a
  slightly less structured entry point than a dedicated picker.

## 5. Summary: what's genuinely zero-code, and what isn't

**Zero code change, works today:**
- Any new `strix/skills/<category>/<name>.md` file (vulnerability
  technique, framework, cloud provider, protocol, tooling playbook, or a
  new standard) is usable immediately via `strix --skill <name>` and by
  any agent's internal skill request.
- A new *standard* skill is also usable in saas today via the
  `custom_instructions` free-text field, even before the picker is
  updated.

**One small, mechanical code change (not a feature build):**
- Making a new standard appear as a checkbox in the saas "New Pentest" /
  "Schedule" picker: two lines in `standard_skills.py`
  (`STANDARD_SKILL_NAMES` + `STANDARD_SKILL_CATALOG`), no frontend edit.
- Making `register_skill_dir()` load from an operator-configured path
  automatically at startup, for teams who want to manage skills as a
  separate private repo rather than editing files under `strix/skills/`.

Both of those are allowlist/wiring edits, not new features — the
knowledge content itself (the thing that actually determines scan
quality and compliance coverage) is always just a markdown file.
