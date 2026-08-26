# SaaS backend configuration

All settings are environment variables with an `SAAS_` prefix (see
`saas/backend/app/settings.py`). Defaults are chosen so the whole app runs
locally with **zero configuration** — every setting below is optional.

| Variable | Default | Effect |
|---|---|---|
| `SAAS_DATABASE_URL` | `sqlite:///./strix_saas.db` | SQLAlchemy connection string. Point at Postgres in production, e.g. `postgresql+psycopg://user:pass@host/db` |
| `SAAS_DEV_MODE` | `true` | When true: OTP codes and invitation tokens are returned directly in API responses instead of emailed; cookies aren't marked `Secure`. Set to `false` once a real email provider is wired up. |
| `SAAS_SESSION_SECRET` | insecure dev value | Change this for any non-local deployment. |
| `SAAS_FRONTEND_ORIGIN` | `http://localhost:5173` | CORS allow-origin for the frontend dev server / deployed frontend. |
| `SAAS_ENABLE_REAL_SCAN` | `false` | When true, pentests invoke the real `strix.core.runner.run_strix_scan` engine (Docker + LLM credentials required) instead of the mock scanner. A repository target is cloned locally first — authenticated with the org's connected GitHub/GitLab credential when there is one — and scanned whitebox; findings are read back from that run's `vulnerabilities.json`. Falls back to mock on any failure (clone failure included), so a pentest never gets stuck. **PR reviews are gated by this same flag, but never fall back to mock** — see "PR reviews: real scan only" below. |
| `SAAS_STRIPE_SECRET_KEY`, `SAAS_STRIPE_WEBHOOK_SECRET` | unset | Set to activate `RealStripeProvider` (see `app/providers/billing.py`) instead of the mock. Requires a Stripe account. |
| `SAAS_CREDENTIALS_ENCRYPTION_KEY` | insecure dev value | Encrypts GitHub/GitLab personal access tokens at rest (see `app/crypto.py`). Any string works (it's hashed into a valid Fernet key) — change it for any non-local deployment, same as `SAAS_SESSION_SECRET`. |

## GitHub / GitLab: real, per-org, token-based (not a GitHub App)

Unlike the rest of this doc's "mock until you register a deployment-wide
app" pattern, GitHub and GitLab integrations are **real by default, per
org** — no app registration, no OAuth consent screen, no deployment-wide
credentials needed. From **Settings → Integrations**, an org admin
connects by supplying:

- **Account/username or group** — whatever the token belongs to
- **Personal/Project Access Token** — required for these two providers
- **Instance URL** (optional) — self-hosted GitLab, or a GitHub Enterprise
  Server, instead of gitlab.com/github.com

On Connect, the token is verified live (`GET /user`) against the real
API before anything is saved — a bad token or unreachable URL fails
immediately with `invalid_credentials` (401) or `provider_unreachable`
(502), not silently on the next scan. The full token is encrypted at rest
(`SAAS_CREDENTIALS_ENCRYPTION_KEY` above) and decrypted only when needed to
make a real API call; only its last 4 characters are additionally kept in
plaintext for display. See `app/providers/git_hosting.py`.

**Scope, deliberately narrow for now:** connecting and listing real repos
(`GET /user/repos` / `GET /projects?membership=true`) — the "Add
Repository" picker on both Repositories and PR Reviews shows real repos
once connected — plus, per repository, real branches/tags/commits (New
Pentest's ref picker) and open pull/merge requests (`GET .../pulls` /
`GET .../merge_requests`, backing "Review a Pull Request"'s PR picker), and,
when `SAAS_ENABLE_REAL_SCAN=1`, authenticating the `git clone` a real
pentest or PR review runs against. Posting real check-runs/PR comments and
receiving webhooks are **not** wired up yet — a PR review's check-run still
posts through the mock GitHub App path
(`app/providers/github.py`'s `get_github_provider()`, unrelated to the
per-org token above — see that file's docstring for why they're
intentionally two separate things), even though the *scan* behind that
check-run is real. An org that hasn't connected GitHub falls back to a
fixed mock repo catalog (so the demo/seed org keeps working with zero
setup) and an unauthenticated clone for real scans (public repos only); an
unconnected GitLab shows nothing to add, since GitLab never had a mock
catalog.

## PR reviews: real scan only, no mock fallback

Unlike pentests, **PR reviews have no mock scanner and no fallback to
one.** Triggering a review (the "Review a Pull Request" button, a GitHub
webhook on PR open/push, or an `@strix` PR comment) requires
`SAAS_ENABLE_REAL_SCAN=1` — the manual trigger endpoint returns `400
real_scan_not_enabled` otherwise, and the webhook silently skips with
`{"skipped": "real_scan_not_enabled"}`.

A triggered review is created immediately with `status="running"` and
enqueued on the same job worker pentests use (one queue, one scan at a
time — see `app/jobs.py`'s module docstring for why a PR-review-specific
second queue would be unsafe). The worker then, for real:

1. Clones the repository and checks out the PR/MR's exact head commit via
   the provider's synthetic ref (`refs/pull/<n>/head` on GitHub,
   `refs/merge-requests/<n>/head` on GitLab) — this resolves correctly even
   for a fork-sourced PR, unlike checking out the PR's plain branch name.
2. Diff-scopes the engine run against the PR's base branch
   (`strix.interface.utils.resolve_diff_scope_context`, the same mechanism
   the strix CLI uses in CI) — the agent's attention goes to the PR's
   actual changed files, not the whole repository.
3. Runs `strix.core.runner.run_strix_scan` in `"quick"` mode and reads back
   real findings from `vulnerabilities.json`, exactly like a real pentest.

If the scan fails for any reason (clone failure, unresolvable base branch,
engine crash), the review lands in `status="failed"` with a short `error`
reason — never silently substituted with canned findings. `target_branch`
and `resolved_head_sha` are persisted on the `PRReview` row for
reproducibility (same rationale as `Pentest.resolved_commit_sha`).

## What else is mocked by default, and why

Two things need credentials only you can provide, so they run against a
mock provider until configured:

1. **Stripe billing** — `MockBillingProvider` flips `card_added` locally
   with no payment processor involved. Real version needs a Stripe account
   and product/price IDs.
2. **Outbound email for OTP codes / invitations** — dev mode returns the
   code/token directly in the API response (see `SAAS_DEV_MODE`). Wiring a
   real provider (Postmark/SES/etc.) means adding a `send_email()` call in
   `app/routers/auth.py`'s `otp_start` and `app/routers/members.py`'s
   `create_invitation`, then setting `SAAS_DEV_MODE=false`.

Everything else (orgs, repos, domains, pentests, issues, PR review
settings, knowledge base, chat, tokens, audit log, and now GitHub/GitLab
connect+list above) is real — backed by the actual database and, for
GitHub/GitLab, real outbound API calls.

## Baseline scan (Tier 3 deterministic coverage)

When `SAAS_ENABLE_REAL_SCAN=1`, every real pentest also runs a
deterministic, non-LLM baseline scan before the agent loop starts — see
`docs/strix-engine-architecture.md` §5.2 and
`docs/scan-coverage-tier3-plan.md` for the full design. It exists because
letting the LLM root agent alone decide whether to spawn a
dependency/secrets/IaC agent produced inconsistent coverage run-to-run on
an identical commit. This is engine-level behavior (`strix/scan/baseline.py`),
not a `saas/`-specific feature, but it's controlled by strix's own env
vars (not `SAAS_`-prefixed) and this deployment needs the underlying tool
binaries on `PATH` for it to do anything:

| Variable | Default | Effect |
|---|---|---|
| `STRIX_BASELINE_SCAN` | `true` | Set to `0`/`false` to disable the baseline scan entirely (agents still cover those categories themselves, just without the deterministic floor or the `finish_scan` cross-check). |
| `STRIX_BASELINE_TIMEOUT` | `180` | Per-tool timeout in seconds. |

| Category | Tool | Binary needed |
|---|---|---|
| Dependencies (SCA) | `trivy fs` | `trivy` |
| Secrets (incl. git history) | `gitleaks detect` | `gitleaks` |
| Infrastructure/IaC | `kube-linter lint` | `kube-linter` |

**A missing binary is not a deployment error** — the baseline scan
degrades gracefully per category (logs a warning, contributes zero
findings for that category) rather than failing the pentest. But a
deployment that wants the deterministic-coverage guarantee needs all
three installed wherever `_run_real_scan` actually executes (the
`saas/backend` worker process host, per its "isolation rule: we never
fork engine code" — see `app/jobs.py`), since the baseline scan runs
host-side against the already-cloned repository, not inside the Docker
sandbox.

Findings the baseline scan files carry `source: "baseline_scan"` on the
resulting `Issue` row (passed straight through from strix's
`vulnerabilities.json`) and render with an "Automatically detected"
badge in the Issues UI; everything an agent found/validated has
`source: null` and no badge.

## Per-org LLM configuration

Each org can set its own model/API base/API key from **Settings → LLM
Provider** in the UI (`GET`/`PATCH /api/settings/llm`, backed by the
`OrgLlmSettings` table) instead of relying on process-wide env vars. When
`SAAS_ENABLE_REAL_SCAN=1`, `app/jobs.py`'s `_run_real_scan` applies that
org's `model`/`api_key`/`api_base` as `STRIX_LLM`/`LLM_API_KEY`/
`LLM_API_BASE` immediately before calling into the strix engine, and
restores the previous env afterward. If an org hasn't configured anything,
the scan falls back to whatever process-wide `STRIX_LLM`/`LLM_API_KEY`/
`LLM_API_BASE` are set (see the root README/`docs/llm-providers/` for those).

**Why this is safe only under today's architecture, and what would break
it:** strix's LLM configuration is a process-global singleton
(`strix/config/loader.py`'s `load_settings()` memoizes once per process)
with no per-call override parameter anywhere in `run_strix_scan`,
`build_strix_agent`, or `RunConfig` — `configure_sdk_model_defaults()`
mutates `os.environ`, litellm's module globals, and the OpenAI-Agents SDK's
global defaults directly. Swapping env vars per-org is only safe because
`app/jobs.py`'s worker processes **one scan at a time** (a single
`asyncio.Queue` consumed by one loop — see its module docstring). If the
worker is ever parallelized to run multiple scans concurrently, this
approach breaks: two orgs' credentials would race. Don't do that without
also isolating each scan (e.g. one subprocess/container per scan) so each
gets its own process-global state.

**Two things flagged for hardening, not yet done:**
- `OrgLlmSettings.api_key` is stored in plaintext in the database — unlike
  `Integration.credential_encrypted` (GitHub/GitLab tokens, above), which
  already uses the same `cryptography` Fernet approach this item asks for.
  Wire `OrgLlmSettings.api_key` through `app/crypto.py` too before any
  shared or production deployment.
- `ApiToken.expires_at` is stored and shown in the UI but **not enforced**
  — there's no bearer-token authentication path in this scaffold at all
  yet (only the session cookie is checked; see `app/deps.py`). Wire actual
  token-based auth before relying on expiration for anything.
