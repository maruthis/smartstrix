---
name: unrestricted_resource_consumption
description: Unrestricted resource-consumption testing covering missing rate limits, pagination abuse, expensive endpoints, and file-size bombs
---

# Unrestricted Resource Consumption

APIs and apps that do not bound work per caller enable account lockout, cost amplification, or denial of service. Prove that an unauthenticated or low-privilege caller can force disproportionate CPU, memory, storage, or third-party spend.

## Attack Surface

- Auth endpoints (login, register, password reset, OTP, token refresh)
- List/search endpoints without pagination caps or with `limit=999999`
- File upload / import / image resize / PDF render / webhook retry
- GraphQL (pair with `graphql` for batching and depth)
- Password hashing endpoints that let the client pick iteration count
- SMS/email/OTP senders (cost amplification)

## Methodology

1. Identify endpoints whose work is CPU-heavy, fan-out, or billed per request
2. Send a small burst first (10–50 requests) — do not run a destructive flood
3. Measure: latency spike, 500s, duplicate side effects, or unbounded payload accepted
4. Stop as soon as impact is demonstrated; this is not a load test of production

## Techniques

### Missing or weak rate limits

- Login / reset / OTP: 50 attempts from one IP or one account with no lockout or CAPTCHA
- Credential stuffing surface: same password across many users with no per-IP throttle
- Authenticated API: tight loop on an expensive handler (`/export`, `/search?q=`)

### Pagination and bulk

- `?page_size=100000` or `limit=-1` returning the whole table
- Negative offsets, `page=0`, GraphQL aliases duplicating a resolver
- CSV/JSON export of all users without authz (also `broken_function_level_authorization` / `idor`)

### Expensive operations and bombs

- Upload a tiny zip-bomb or a large `Content-Length` with a slow body (stop at first 413/timeout that proves no cap)
- Image/PDF processors: pixel-flood (`100000x100000`) or recursive entity expansion (pair with `xxe`)
- Redirect loops or SSRF-to-self that amplifies (pair with `ssrf`) — one demonstration request, not a loop
- Webhook endpoints that synchronously call out per event with no cap

## Validation

- Never run an unbounded flood. A finding is "N unauthenticated requests in T seconds produced X" — not "I could have sent more"
- HTTP 429 on some paths does not mean every expensive path is limited — test the ones that hash, send mail, or touch object storage
- Cite CWE-770 / CWE-400 / CWE-307 / CWE-799 and the mapped standard ID when a standards skill is loaded
