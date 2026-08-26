---
name: security_misconfiguration
description: Security misconfiguration testing covering CORS, headers, default creds, debug surfaces, and cookie flags
---

# Security Misconfiguration

Misconfiguration is the default-insecure leftover: debug endpoints, default credentials, permissive CORS, missing security headers, directory listing, and admin panels left on the internet. Prove that the leftover is reachable and that it grants something a locked-down config would not. For **source-level** fail-open defaults (`getenv("JWT_SECRET") or "dev"`), use `insecure_defaults`.

## Attack Surface

- HTTP security headers, CORS, cookies
- Admin/debug/actuator/profiler/graphql playground
- Default or sample credentials, setup wizards still enabled
- Directory listing, backup files, `.git`, `.env`, stack traces
- Cloud storage ACLs, overly broad security groups (when in scope)
- Framework debug mode (`DEBUG=true`, Django traceback, Spring Actuator)

## Methodology

1. Fingerprint stack (headers, cookies, error pages, JS sourcemaps)
2. Hit a shortlist of high-signal misconfig paths before deep fuzzing
3. Confirm impact: data leak, auth bypass, or a foothold — not "header missing" alone unless the missing header enables a specific attack you demonstrated
4. For CORS, prove credentialed cross-origin read or a CSRF-relevant ACAO reflection

## Techniques

### CORS

- `Origin: https://evil.example` reflected in `Access-Control-Allow-Origin` with `Access-Control-Allow-Credentials: true`
- Null origin (`Origin: null`) accepted
- Prefix/suffix bypasses (`https://target.com.evil.com`, `https://target.com.evil`)
- Dynamic origin allowlists that trust `endsWith(target.com)`

### Headers and cookies

- Missing or weak `Content-Security-Policy` only if you can actually XSS (pair with `xss`)
- Clickjacking: missing `X-Frame-Options` / `frame-ancestors` **and** a state-changing page that loads in a frame
- Cookies without `HttpOnly`/`Secure`/`SameSite` — prove theft or CSRF, do not file the flag alone on an API bearer-token app
- `X-Powered-By` / `Server` version disclosure is informational unless it reveals a known-vulnerable build you can exploit

### Debug, defaults, leftovers

- `/actuator`, `/debug`, `/phpinfo.php`, `/graphql`, `/_profiler`, `/admin` with default creds (`admin:admin`, vendor docs)
- Stack traces returning paths, connection strings, or framework versions
- Directory listing → backup zips, `.DS_Store`, `web.config.bak`
- `.git/HEAD` or `.svn` exposed — clone enough to recover source
- Setup/install routes (`/install`, `/wp-admin/install.php`) on a live site

## Validation

- A missing security header is not a finding unless you show the attack it enables
- Default credentials: authenticate successfully, then stop — do not dump production data
- Cite CWE-16 / CWE-215 / CWE-942 / CWE-200 / CWE-798 and the mapped standard ID when a standards skill is loaded
