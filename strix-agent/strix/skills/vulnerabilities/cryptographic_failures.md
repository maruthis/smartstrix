---
name: cryptographic_failures
description: Cryptographic failure testing covering TLS, weak hashing, secrets at rest, and cookie/token crypto
---

# Cryptographic Failures

Crypto failures leak or forge data when the app uses broken algorithms, custom crypto, missing encryption, or misconfigured TLS. Prefer proving a concrete confidentiality or integrity break over flagging a library version.

## Attack Surface

- TLS termination (load balancer, CDN, app server) and certificate chain
- Password storage, API key hashing, backup encryption
- Cookies, session tokens, CSRF tokens, password-reset tokens
- Data at rest (DB columns, object storage, backups, logs)
- JWT/JWE (pair with `authentication_jwt` for alg confusion)
- Client-side crypto that the server later trusts

## Methodology

1. Enumerate every channel that claims to protect data (HTTPS, hashed passwords, encrypted fields, signed cookies)
2. Identify algorithm, key source, and whether the server actually verifies it
3. Prove impact: decrypt, forge, downgrade, or recover a secret faster than a brute-force budget
4. File only with a working PoC (captured plaintext, forged cookie, or cracked hash)

## Techniques

### TLS / transport

- Check certificate validity, hostname, chain, and mixed-content HTTP subresources
- Probe protocol/cipher downgrade (`sslscan`, `nmap --script ssl-*`, `testssl.sh` if present)
- Confirm HSTS is actually sent and covers subdomains when the app uses them
- Hit the same host on `:80` and look for open redirects or cookie issuance over HTTP
- Cloud/CDN: origin still speaking HTTP behind TLS at the edge is a finding only if you can reach the origin

### Password and secret storage

- Register, reset password, or dump a hash from whitebox (`bcrypt`/`argon2` vs `md5`/`sha1`/`sha256` unsalted)
- Fast-hash + no salt is reportable with a crack demonstration on a test account you created
- Secrets in source, env samples, CI logs, object-storage ACLs — confirm they still authenticate
- Hard-coded HMAC/JWT secrets in frontend bundles or public repos

### Tokens and cookies

- Session cookie missing `Secure` over HTTPS, or issued on HTTP
- Predictable tokens (timestamp, incrementing id, truncated hash of email)
- Encrypted-but-not-authenticated cookies (CBC padding oracle, bit-flip to change `role=user`)
- Short-entropy reset tokens (`/reset?token=` with <64 bits)

### Data at rest

- PII or payment data stored plaintext in DB/backups
- Encrypted columns with the key beside them (`ENCRYPTION_KEY=` in the same config)
- Client-side "encryption" with a key shipped in JS

## Validation

- Do not report "TLS 1.0 might be enabled" without a successful handshake you captured
- Do not report a CVSS for a library CVE here — use `create_dependency_report` / `dependency_cve_scanning`
- Weak password policy belongs in `weak_password_detection`; this skill is the crypto primitive, not the policy
- Cite CWE-327 / CWE-326 / CWE-311 / CWE-798 / CWE-319 and the mapped standard ID when a standards skill is loaded
