---
name: owasp_asvs
description: OWASP ASVS L1/L2 coverage map — technically testable chapters only, mapped to specialist skills
---

# OWASP ASVS (L1/L2, testable)

Coverage index for ASVS chapters a pentest can actually exercise. Spawn specialists for every chapter that applies. Tag findings `ASVS Vx.y.z` (nearest requirement) plus CWE.

Out of scope: architecture review workshops, documented SDLC, physical security, HR, and requirements that only a paper policy can satisfy. L3 (e.g. high-assurance crypto design) is out unless the user asked for it.

## Mandatory coverage (testable chapters)

| Chapter | Focus | Spawn with skills |
|---|---|---|
| V2 Authentication | Login, MFA, recovery, authenticators | `authentication_jwt`, `weak_password_detection` |
| V3 Session | Fixation, timeout, rotation, cookies | `session_management` |
| V4 Access control | Deny by default, IDOR, BFLA | `idor`, `broken_function_level_authorization` |
| V5 Validation / sanitization | Injection, XSS, SSRF, XXE, uploads | `sql_injection`, `xss`, `ssrf`, `xxe`, `insecure_file_uploads`, `header_injection` |
| V6 Cryptography | TLS, stored secrets, random | `cryptographic_failures` |
| V7 Erroring / logging | Stack traces, log injection (observable only) | `information_disclosure` |
| V8 Data protection | PII in URLs, cache, backups | `information_disclosure`, `cryptographic_failures` |
| V9 Communication | TLS to backends, cookie Secure | `cryptographic_failures`, `security_misconfiguration` |
| V10 Malicious code | Not a pentest chapter — skip unless whitebox reveals backdoors |
| V11 Business logic | Workflow, race, mass assignment, resource limits | `business_logic`, `race_conditions`, `mass_assignment`, `unrestricted_resource_consumption` |
| V12 Files | Path traversal, upload, LFI | `path_traversal_lfi_rfi`, `insecure_file_uploads` |
| V13 API | Mass assignment, BFLA, rate limit | `mass_assignment`, `broken_function_level_authorization`, `unrestricted_resource_consumption` |
| V14 Configuration | Headers, CORS, debug, defaults | `security_misconfiguration` |

## Spawn rules

- Prefer L1/L2 checks: "can a remote attacker break this?" not "is there a written key-management policy?"
- GraphQL / OAuth / JWT stacks: also load `graphql` / `oauth` / `authentication_jwt` on the matching specialist
- When filing: `ASVS V4.2.1 — CWE-639 — <one-line issue>`
