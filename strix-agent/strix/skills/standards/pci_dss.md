---
name: pci_dss
description: PCI DSS 4.0 technical subset — testable requirements 2, 4, 6, 8, 11 mapped to specialist skills
---

# PCI DSS 4.0 (technical subset)

Coverage index for **technically testable** PCI DSS 4.0 requirements that show up in an application/API pentest. Spawn specialists for every row that has surface. Tag findings `PCI DSS 4.0 Req x.y` plus CWE.

**Out of scope (do not invent gaps):** policies, SAQ paperwork, physical CCTV, HR background checks, vendor contracts, 3.x key-ceremony documentation, 9.x physical access, 12.x governance. If the user asked for a "PCI pentest," still only test the rows below.

## Mandatory coverage (testable)

| Req | Intent | Spawn with skills |
|---|---|---|
| 2.x | Secure configs, no vendor defaults | `security_misconfiguration`, `weak_password_detection` |
| 4.x | Strong crypto in transit | `cryptographic_failures` |
| 6.2 / 6.3 | Custom code, injection, XSS, CSRF, authz | `sql_injection`, `xss`, `csrf`, `idor`, `broken_function_level_authorization`, `ssti` |
| 6.4 | Public-facing web — file upload, path traversal, SSRF | `insecure_file_uploads`, `path_traversal_lfi_rfi`, `ssrf` |
| 6.5 | Change / live vulns — SCA when source is present | `dependency_cve_scanning` |
| 8.x | Identity — passwords, MFA surfaces, session | `authentication_jwt`, `session_management`, `weak_password_detection` |
| 11.3 | App-layer pentest (this scan) | Honor every other row; do not skip because "11.3 is the pentest itself" |

## Spawn rules

- Cardholder data in logs, verbose errors, or URLs: `information_disclosure` + Req 3.x/6.x only if you **observed** PAN/SAD — never exfiltrate live card data; use test PANs
- TLS issues are Req 4.x, not a generic "misconfig" unless headers/CORS are the actual bug
- When filing: `PCI DSS 4.0 Req 6.2.4 — CWE-89 — <one-line issue>`
