---
name: springboot
description: Security testing playbook for Spring Boot applications covering actuators, SpEL, method security, native queries, JWT filters, and misconfiguration
---

# Spring Boot

Security testing for Spring Boot / Spring Security services (MVC, WebFlux, Spring Data, Cloud). Focus on exposed actuators, SpEL injection, missing method security, native-query concatenation, and JWT/filter-order bugs.

## Attack Surface

**HTTP**
- `@RestController` / `@Controller`, functional WebFlux routers
- Filters (`OncePerRequestFilter`), interceptors, CORS, CSRF
- OpenAPI (`springdoc`, `/swagger-ui`, `/v3/api-docs`)

**Security**
- `SecurityFilterChain`, `authorizeHttpRequests`, `requestMatchers`
- `@PreAuthorize` / `@PostAuthorize` / `@Secured` (only if `@EnableMethodSecurity`)
- JWT resource server, opaque tokens, session cookies
- OAuth2 login / client

**Data**
- Spring Data JPA derived queries vs `@Query` / native SQL
- JDBC `NamedParameterJdbcTemplate` vs string concat
- Jackson / Gson binding onto entities (`@JsonIgnore` gaps)

**Ops / cloud**
- Actuator (`/actuator/*`), H2 console, heapdumps
- Spring Cloud Config / Bus, Eureka, Zipkin
- Thymeleaf / Mustache / FreeMarker templates

## High-Value Targets

- `/actuator/env`, `/actuator/heapdump`, `/actuator/gateway`, `/actuator/mappings`, `/actuator/jolokia`
- `/h2-console`, `/swagger-ui.html`, `/v3/api-docs` unauthenticated
- Endpoints with CSRF disabled **and** cookie-based auth
- Native queries concatenating sort/filter: `"ORDER BY " + param`
- SpEL in `@PreAuthorize`, `@Value("#{...}")`, logging patterns, Thymeleaf `__${}__`
- JWT filter that sets `SecurityContext` without signature/issuer/audience checks
- Entities bound directly from `@RequestBody` (mass assignment of `roles`, `balance`)

## Reconnaissance

**Fingerprinting**
```
GET /actuator            GET /actuator/health
GET /actuator/env        GET /actuator/mappings
GET /v3/api-docs         GET /swagger-ui/index.html
GET /h2-console
Set-Cookie: JSESSIONID / headers: X-Application-Context
pom.xml / build.gradle: spring-boot-starter-actuator, spring-security
```

**White-box greps**
```
authorizeHttpRequests    permitAll
csrf.disable
@PreAuthorize            @Query(nativeQuery = true)
createNativeQuery        EntityManager.createQuery
#{#            T(java.lang.Runtime)
management.endpoints.web.exposure.include
```

## Key Vulnerabilities

### Actuator and debug surfaces

- `management.endpoints.web.exposure.include=*` plus no auth → env secrets, heapdump (credentials in memory), gateway routes
- Jolokia / restart / shutdown / logfile as RCE or DoS
- H2 console with default or weak auth
- `server.error.include-stacktrace=always` / `include-message=always`

### Method security gaps

- HTTP matcher `authenticated()` but no object-level check → IDOR
- `@PreAuthorize` on some methods, missing on siblings (`GET` protected, `PATCH` not)
- `@EnableMethodSecurity` not enabled → annotations are no-ops
- SpEL that uses attacker-controlled method args: `@PreAuthorize("#id == authentication.name")` bypass via type confusion

### SpEL injection

- User input interpolated into SpEL (`@PreAuthorize`, evaluation context, Thymeleaf preprocessing `[[${param}]]` / `__${}__`)
- Log patterns / error pages evaluating expressions
- Impact: RCE via `T(java.lang.Runtime).getRuntime().exec(...)` when evaluation is unconstrained

### Injection / ORM

- Native `@Query("... " + user)` or `createNativeQuery` concat
- JPQL injection via `ORDER BY` / entity-name concatenation
- Mass assignment: JPA entity as DTO; client sets `admin`, `enabled`, nested `user.roles`
- Jackson `enableDefaultTyping` / polymorphic `@JsonTypeInfo` → gadget deserialization (see `insecure_deserialization`)

### Authn / CSRF / CORS

- `csrf.disable()` on a browser-session app (not a pure Bearer API)
- JWT parsed with `parser().parse(token)` (no verify) or `none` alg
- Filter order: JWT filter after anonymous; public matcher too broad (`/**`)
- CORS `allowedOriginPatterns("*")` + `allowCredentials(true)`
- `SessionCreationPolicy.STATELESS` while still using cookies

### SSTI / template

- Thymeleaf fragment names or layout names from request params
- FreeMarker `?new` / `ObjectConstructor` if poorly configured
- Error pages reflecting unsanitized exceptions

## Testing Methodology

1. Enumerate actuators, swagger, H2, env dumps before business logic
2. Diff `SecurityFilterChain` matchers vs controller methods — find permitAll and missing `@PreAuthorize`
3. For every entity-binding endpoint, add privileged JSON fields
4. Fuzz sort/search into native queries; probe SpEL metacharacters on annotated methods
5. IDOR across path IDs with a low-privilege JWT
6. Confirm CSRF: cookie session + state-changing POST without token
7. Check JWT: alg confusion, expired, wrong `aud`/`iss`, path traversal in `kid`

## Validation

- Actuator: actual secret, heapdump, or route mutation — not just 200 on `/health`
- Authz: another user's resource read/written
- SpEL/SSTI: command execution or file read, not just expression echo
- SQLi: row set change or error-based proof
- CSRF: state change from a foreign origin with the victim cookie

## False Positives

- `/actuator/health` only, no extra endpoints, no details
- CSRF disabled on a documented Bearer-only API with no cookie auth
- Derived Spring Data queries (auto-parameterized)
- `@PreAuthorize` with constant role checks and no user-controlled SpEL

## Impact

- Credential and secret theft (actuator env/heapdump)
- Horizontal/vertical privilege escalation
- RCE (SpEL, deserialization, Jolokia)
- Full data store compromise via native SQL

## Pro Tips

1. `management.endpoints.web.base-path` is often not `/actuator` — try `/manage`, `/ops`, from `mappings`
2. Heapdump is high severity even when `env` is locked down
3. If `@EnableMethodSecurity` is missing, treat every `@PreAuthorize` as unenforced
4. Spring Cloud Gateway actuators rewrite routes — SSRF and proxy abuse
5. Pair this skill with `authentication_jwt`, `idor`, and `insecure_deserialization`
