---
name: owasp_api_top_10
description: OWASP API Security Top 10:2023 coverage map — spawn specialists for every API category that has surface
---

# OWASP API Security Top 10:2023

Coverage index for API targets (REST, GraphQL, gRPC-JSON, RPC). Spawn a specialist for **every** row that applies. Tag findings `OWASP API1:2023` (etc.) plus CWE.

Out of scope: inventory spreadsheets the org maintains offline, and WAF product selection.

## Mandatory coverage

| ID | Category | Spawn with skills |
|---|---|---|
| API1:2023 | Broken Object Level Authorization | `idor` |
| API2:2023 | Broken Authentication | `authentication_jwt`, `session_management`, `weak_password_detection` |
| API3:2023 | Broken Object Property Level Authorization | `mass_assignment`, `information_disclosure` |
| API4:2023 | Unrestricted Resource Consumption | `unrestricted_resource_consumption` |
| API5:2023 | Broken Function Level Authorization | `broken_function_level_authorization` |
| API6:2023 | Unrestricted Access to Sensitive Business Flows | `business_logic`, `race_conditions` |
| API7:2023 | Server Side Request Forgery | `ssrf` |
| API8:2023 | Security Misconfiguration | `security_misconfiguration` |
| API9:2023 | Improper Inventory Management | `information_disclosure` |
| API10:2023 | Unsafe Consumption of APIs | `ssrf`, `insecure_deserialization`, `xxe` |

## Spawn rules

- API9: shadow/versioned routes (`/v1` vs `/v2`, `/internal`, docs vs reality). Whitebox: grep routers
- API10: trust of third-party webhooks, parsed responses, callbacks
- If an OpenAPI/Postman spec is in scope, walk **declared** endpoints first, then hunt undocumented ones (API9)
- GraphQL: add `graphql` to API1/API3/API4 specialists (batching, field-level authz, depth)
- When filing: `OWASP API4:2023 — CWE-770 — <one-line issue>`
