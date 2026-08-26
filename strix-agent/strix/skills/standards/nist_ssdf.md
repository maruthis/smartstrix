---
name: nist_ssdf
description: NIST SSDF + 800-53 technical overlay (SA, SI, SC, IA, AC) — testable engineering controls only
---

# NIST SSDF + 800-53 (technical overlay)

Coverage index for **testable** NIST SSDF practices and overlapping 800-53 families (AC, IA, SC, SI, SA). Spawn specialists for every row with surface. Tag findings `NIST SSDF <practice>` or `NIST 800-53 <control>` plus CWE.

**Out of scope:** POA&M process, FedRAMP paperwork, organization-level continuous monitoring contracts, personnel controls, physical controls.

## Mandatory coverage (testable)

| SSDF / 800-53 | Intent | Spawn with skills |
|---|---|---|
| PO.5 / SA-11 | Test before release — injection, XSS, SSRF | `sql_injection`, `xss`, `ssrf`, `xxe` |
| PW.4 / SA-15 | Design threats — business logic, races | `business_logic`, `race_conditions` |
| PW.5 / SI-10 | Input validation | `sql_injection`, `xss`, `header_injection`, `insecure_file_uploads` |
| PW.6 / SI-16 | Memory / integrity of interpreted code | `insecure_deserialization`, `ssti`, `rce` |
| PW.8 / SA-10 | Reviewed, pinned dependencies | `dependency_cve_scanning` (whitebox) |
| PW.9 / SI-7 | Integrity of software — uploads, deserial | `insecure_file_uploads`, `insecure_deserialization` |
| RV.1 / RA-5 | Known vulns in components | `dependency_cve_scanning` |
| AC-3 / AC-6 | Least privilege, IDOR, BFLA | `idor`, `broken_function_level_authorization` |
| IA-2 / IA-5 | Auth, authenticators, crypto for secrets | `authentication_jwt`, `weak_password_detection`, `cryptographic_failures` |
| SC-8 / SC-13 | In-transit / at-rest crypto | `cryptographic_failures` |
| SC-5 | DoS / resource control | `unrestricted_resource_consumption` |
| SC-7 / CM-7 | Exposed admin, unnecessary services | `security_misconfiguration` |
| SI-11 | Error handling — fail-open, traces | `information_disclosure`, `security_misconfiguration` |
| AC-12 | Session termination | `session_management` |

## Spawn rules

- This overlay does **not** replace OWASP maps; if both are loaded, merge rows and spawn each skill at most once
- When filing: `NIST 800-53 AC-3 — CWE-639 — <one-line issue>` (or `NIST SSDF PW.5.1` when the SSDF practice is the better fit)
