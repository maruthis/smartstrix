---
name: owasp_top_10
description: OWASP Top 10:2025 coverage map — spawn specialists for every testable category and tag findings with A0x + CWE
---

# OWASP Top 10:2025

Coverage index, not a playbook. You are the root agent: spawn a specialist for **every** row below that has any surface on this target. Do not skip a row because recon ranked it low. Cite `OWASP A0x:2025` and the CWE in each `create_vulnerability_report` description.

Out of scope for this map: organizational policy, security-champion programs, and production logging pipelines you cannot observe from the target.

## Mandatory coverage

| ID | Category | Spawn with skills | Notes |
|---|---|---|---|
| A01:2025 | Broken Access Control | `idor`, `broken_function_level_authorization`, `path_traversal_lfi_rfi`, `csrf` | Horizontal/vertical IDOR, BFLA, path traversal, CSRF on cookie auth |
| A02:2025 | Security Misconfiguration | `security_misconfiguration` | CORS, headers, debug, defaults, leftovers |
| A03:2025 | Software Supply Chain Failures | `dependency_cve_scanning` | Lockfiles, CI, unsigned artifacts. Whitebox: mandatory SCA agent already required |
| A04:2025 | Cryptographic Failures | `cryptographic_failures` | TLS, hashing, secrets at rest, cookie crypto |
| A05:2025 | Injection | `sql_injection`, `xss`, `ssti`, `xxe`, `header_injection`, `nosql_injection` | Pick the dialect the stack uses; do not spawn all six if the target has no XML/NoSQL |
| A06:2025 | Insecure Design | `business_logic`, `race_conditions`, `mass_assignment` | Workflow bypass, TOCTOU, hidden fields |
| A07:2025 | Authentication Failures | `authentication_jwt`, `session_management`, `weak_password_detection` | JWT/OIDC, session lifecycle, password policy |
| A08:2025 | Software or Data Integrity Failures | `insecure_deserialization`, `insecure_file_uploads` | Gadgets, unsigned updates, upload → exec |
| A09:2025 | Security Logging Failures | `information_disclosure` | Only what is testable: auth events missing, verbose errors, log injection. Do not invent SIEM gaps |
| A10:2025 | Mishandling of Exceptional Conditions | `security_misconfiguration`, `information_disclosure` | Uncaught errors, fail-open authz, stack traces, timeout → bypass |

## Spawn rules

- One specialist per row is enough when skills are related; split Injection if SQL and XSS both have real surface
- SSRF (`ssrf`) is not its own Top 10 row in 2025 — still spawn it when the app fetches URLs; tag the finding CWE-918 and note it under A01 or A05 as appropriate
- `unrestricted_resource_consumption` is API Top 10 API4; spawn it when the target is an API even if this map is the only standards skill loaded
- When filing, first line of description: `OWASP A0x:2025 — CWE-NNN — <one-line issue>`
