---
name: session_management
description: Session-management testing covering fixation, timeout, rotation, concurrent sessions, and cookie flags
---

# Session Management

Session failures let an attacker bind, steal, or keep a victim's authenticated state. Treat cookies, server sessions, and opaque tokens as one lifecycle: issue, bind, rotate, expire, revoke.

## Attack Surface

- Login, logout, password change, MFA step-up, impersonation
- Session cookies vs server-side session store vs JWT-as-session
- Absolute vs idle timeout, concurrent device limits
- Cookie `Domain`/`Path`/`Secure`/`HttpOnly`/`SameSite`

## Methodology

1. Map how the session identifier is issued and where it is stored
2. Test fixation (pre-login id accepted post-login) and rotation (password change / privilege change)
3. Test timeout, logout, and revocation (does logout actually kill the server session?)
4. Test cookie scope (parent domain, subdomain) and transport (HTTP vs HTTPS)

## Techniques

### Fixation and rotation

- Set a session cookie (or `?SESSIONID=`) before login; after login, check if the same id is still authenticated
- Change password or MFA settings: old session must die
- Privilege change (user → admin): session id must rotate

### Timeout and logout

- Idle timeout: wait / rewind nothing — send a keep-alive vs a real action after the documented idle window
- Absolute timeout: a long-lived cookie that never expires is a finding if you can still use it days later on a test account
- Logout: replay the cookie; if the server still accepts it, logout is client-side only
- "Logout all devices" that only clears the current cookie

### Concurrency and binding

- Two simultaneous sessions for the same user when the product claims single-session
- Session not bound to User-Agent / IP when the app documents that binding — only report if the product claims it
- Session token in URL (`;jsessionid=`, `/account?sid=`) leaks via Referer

### Cookie flags and scope

- `Domain=.parent.com` leaking a session to an attacker-controlled subdomain
- Missing `Secure` on an HTTPS app so the cookie is sent to `http://`
- Missing `HttpOnly` plus any XSS (chain with `xss`)

## Validation

- Do not file "session cookie without SameSite=Strict" on a pure Bearer-token SPA unless cookies are actually used for auth
- JWT lifetime issues belong primarily in `authentication_jwt`; use this skill when the JWT is the session (no server revoke list)
- Cite CWE-384 / CWE-613 / CWE-614 / CWE-1004 / CWE-1275 and the mapped standard ID when a standards skill is loaded
