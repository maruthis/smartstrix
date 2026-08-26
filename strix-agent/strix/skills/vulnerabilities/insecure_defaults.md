---
name: insecure_defaults
description: Testing fail-open defaults — hardcoded fallback secrets, default credentials, weak crypto, and security that stays off when env vars are missing
---

# Insecure Defaults

Find configuration that **runs insecurely** when a secret, flag, or env var is absent. Crash-on-missing-config is fail-secure (usually not a finding). A hardcoded JWT secret, `AUTH_REQUIRED=false` default, or `or "changeme"` fallback is fail-open and exploitable in any environment that forgot to set the variable — including production.

This is distinct from `security_misconfiguration` (live leftover panels, CORS, headers). Here the bug is in **source**: the default value itself.

## Attack Surface

- `os.getenv("X", "insecure")`, `process.env.X || "secret"`, `ENV.fetch("X", "default")`, `os.environ.get("X") or "fallback"`
- Docker `ENV JWT_SECRET=dev`, Compose `environment:` with real-looking keys
- Helm/K8s `values.yaml` default passwords, Terraform `default = "admin"`
- Framework DEBUG/CSRF/AUTH flags defaulting to the unsafe side
- Crypto: MD5/SHA1 password hashes, DES/ECB, empty or static IVs, `SECRET_KEY` in settings.py committed

## High-Value Targets

- JWT / session / CSRF signing keys with string fallbacks
- Database, Redis, SMTP, cloud API keys in source or `.env.example` that the app actually loads
- `CORS_ORIGINS=*`, `ALLOWED_HOSTS=*`, `AUTH_DISABLED=true` as defaults
- Admin bootstrap users (`admin`/`admin`) created when the user table is empty
- Feature flags: `REQUIRE_MFA`, `RATE_LIMIT`, `EMAIL_VERIFY` defaulting to off

## Reconnaissance

```
getenv(  os.environ.get  process.env.  ENV.fetch  os.Getenv(
\|\| ['\"]  , ['\"]changeme  default=True  DEBUG = True
SECRET_KEY  JWT_SECRET  APP_KEY
Dockerfile  docker-compose  values.yaml  .env.example
```

Trace each hit to runtime: is the fallback used when the var is unset, or only in tests?

## Key Vulnerabilities

### Fallback secrets

```
SECRET = os.getenv("JWT_SECRET") or "dev-secret-do-not-use"
```

If production deploy omits `JWT_SECRET`, tokens are forgeable. Confirm by minting a token with the fallback (in the sandbox against the authorized target), not by guessing live production keys you do not own.

### Fail-open security

- `AUTH_REQUIRED = os.getenv("AUTH_REQUIRED", "false")`
- Middleware that skips auth when the API key header is missing *and* `API_KEY` env is unset
- TLS verify `False` by default, overridden only if `VERIFY_TLS=true`

### Default credentials

- Seeded `admin@localhost` / `password` in migrations
- Vendor appliance defaults still accepted (`admin`/`admin`, `root`/`root`)
- Documented demo users left in `createsuperuser` scripts

### Weak crypto defaults

- Hashers defaulting to MD5/SHA1; JWT `algorithm` defaulting to `none` or `HS256` with a short secret
- Cookie signing with an empty secret when env is blank (some frameworks use `""` rather than refusing to boot)

## Testing Methodology

1. List every security-relevant env/config key and its default
2. Classify fail-open vs fail-secure (does the process refuse to start?)
3. For fail-open secrets: prove the fallback is the live signing/encryption key or credential
4. For flags: run the target without that env (or with it unset in a local/staging copy in scope) and show auth/crypto is actually off
5. Check IaC/Docker for the same defaults baked into images

## Validation

- Show the default value in source **and** that the running app uses it (forged token accepted, unauthenticated privileged call, login with seeded creds)
- Fail-secure crash / `ImproperlyConfigured` is not a vulnerability
- Test-only fixtures never imported by the production entrypoint are not findings
- `.env.example` placeholders that are not loaded at runtime are documentation, not secrets — unless the app reads `.env.example` as fallback

## False Positives

- `os.getenv("X") or ""` followed by an explicit empty-check that aborts
- Defaults used only under `if DEBUG` / `if app.testing`
- Placeholder strings that cannot verify a real token (`changeme` rejected by length checks)

## Impact

- Full auth bypass (forged sessions, disabled auth)
- Credential stuffing against known defaults
- Cross-environment key reuse (dev secret in prod)

## Pro Tips

1. The interesting bug is often "prod Helm chart does not set `JWT_SECRET`" plus a code fallback — check both
2. Empty string is a worse default than a crash: `getenv("KEY") or ""` still starts
3. Pair with `authentication_jwt`, `cryptographic_failures`, and `exploitability_triage`
4. Do not file "use bcrypt" as a default-crypto finding unless you show the actual hasher in the login path
