---
name: laravel
description: Security testing playbook for Laravel applications covering mass assignment, Eloquent raw SQL, Blade XSS, Sanctum, signed URLs, Livewire, and queue jobs
---

# Laravel

Security testing for Laravel (and Lumen) apps, including Breeze/Jetstream, Sanctum, Passport, Livewire, and Inertia. Focus on mass assignment, Eloquent raw-query sinks, Blade unescaping, debug leakage, and authz gaps in policies/gates.

## Attack Surface

**HTTP / routing**
- `routes/web.php`, `routes/api.php`, `routes/console.php`, route groups, signed routes
- Controllers, Form Requests, middleware (`auth`, `can`, `abilities`, `throttle`)
- Blade / Livewire / Inertia / Vue/React frontends

**Eloquent / data**
- Models: `$fillable`, `$guarded`, `$hidden`, `$casts`
- Query builder: `whereRaw`, `orderByRaw`, `selectRaw`, `DB::raw`, `DB::unprepared`
- Serializers / API Resources that leak hidden attributes

**Auth**
- Session cookies (`web` guard), Sanctum SPA cookies + personal access tokens, Passport OAuth
- Gates / policies, Spatie permission packages
- Password reset, email verification, signed URLs (`URL::temporarySignedRoute`)

**Jobs / files**
- Queues (`ShouldQueue`, `SerializesModels`, `unserialize` of job payloads)
- Storage disks, public disk, `Storage::url`, file uploads
- Artisan commands and scheduled tasks accepting user input

## High-Value Targets

- `/telescope`, `/horizon`, `/log-viewer`, `/_debugbar`, `/pulse` in production
- `APP_DEBUG=true` Whoops pages (env, SQL, secrets)
- Models with `$guarded = []` or `Model::create($request->all())`
- Admin CRUD that binds `is_admin`, `role`, `email_verified_at`, `balance`
- Sanctum `/sanctum/csrf-cookie` + SPA on extra origins in `SANCTUM_STATEFUL_DOMAINS`
- File download via `Storage::download` / `response()->file` with user-supplied paths
- Livewire components that hydrate public properties from the client
- Queue workers consuming jobs with attacker-controlled class/payload

## Reconnaissance

**Fingerprinting**
```
GET /  (laravel_session, XSRF-TOKEN, laravel_telescope cookies)
GET /favicon.ico
GET /telescope  /horizon  /_ignition  /_debugbar
composer.json / composer.lock: laravel/framework version
.env.example, config/app.php, config/sanctum.php
```

**White-box greps**
```
$guarded = []
$request->all()
$request->input()
whereRaw(  orderByRaw(  selectRaw(  DB::raw(
{!! $
unserialize(
URL::temporarySignedRoute
Gate::before
->withoutMiddleware
```

## Key Vulnerabilities

### Mass assignment

- `$guarded = []` or missing `$fillable` lets clients set `is_admin`, `role_id`, `price`, `owner_id`
- `User::create($request->all())` / `->update($request->all())` / `->fill($request->all())`
- JSON API that maps request body 1:1 onto Eloquent
- Test: register/update with extra fields; confirm privileged columns stick

### Eloquent / SQL injection

- `whereRaw("email = '$input'")`, `orderByRaw($sort)`, `selectRaw($cols)` without bindings
- `DB::unprepared`, `whereRaw` with concatenated LIKE
- Search/sort/filter query params are the usual source
- Parameterized `whereRaw('email = ?', [$input])` is not a finding

### Blade / XSS

- `{!! $userInput !!}` / `{!! $markdown !!}` without sanitization
- `Js::from` vs concatenating into inline `<script>`
- Livewire `wire:model` reflecting unsanitized HTML; Inertia shared props rendered unsafely
- Stored XSS in comments, bios, markdown fields

### Authn / session

- `APP_KEY` leak (debug page, `.env` in webroot, git) → forge cookies / signed URLs
- Session cookie without `secure`/`httpOnly`/`same_site`
- Sanctum tokens with `['*']` abilities or never-expiring tokens
- `SANCTUM_STATEFUL_DOMAINS` including attacker-controlled hosts → CSRF on SPA cookie auth
- Password reset tokens in logs or over HTTP

### Authorization

- Missing `$this->authorize()` / `Gate::authorize` on show/update/destroy
- Policies that check authentication but not ownership (`return $user !== null`)
- `Gate::before` returning `true` for a loosely assigned role
- Route-level `can:update,post` skipped on API resource extra actions

### Signed URLs and files

- Unsigned download/preview that takes `path` / `disk` / `filename`
- Signed URLs with long expiry or without `hasValidSignature`
- Path traversal in `storage_path($request->file)` / `public_path`
- Uploads stored on the `public` disk with executable extensions

### Livewire / Inertia / queues

- Livewire: mutating public properties (`$userId`, `$role`) from the client; missing `#[Locked]`
- Inertia: trusting client-sent `auth.user.role` instead of server session
- Queues: gadget chains if job payload is attacker-influenced; `unserialize` of user data
- `SerializesModels` IDs swapped to another tenant's model

## Testing Methodology

1. Map routes (`php artisan route:list` or `routes/*.php`) and auth middleware
2. Hit debug/telescope/horizon; confirm they 404 in production
3. For every create/update, send extra privileged attributes
4. Fuzz sort/filter/search into `*Raw` sinks
5. Walk object IDs across users (IDOR) on every resource controller
6. Abuse signed/file/Livewire endpoints with path and property tampering
7. Check Sanctum CSRF + origin and token abilities

## Validation

- Mass assignment: extra field persisted (admin flag, owner change, price)
- SQLi: different row set, error-based proof, or stacked query effect
- XSS: script execution in another user's session
- IDOR: read/write another tenant's model without their session
- File: read outside intended disk or stored executable reachable via URL

## False Positives

- `$fillable` that cannot reach privileged columns
- Bound `whereRaw('... ?', [$input])`
- Telescope/Horizon behind auth on a non-production host
- `{!! !!}` wrapping already-sanitized, trusted CMS HTML with a real sanitizer

## Impact

- Account takeover (cookie forge via `APP_KEY`, XSS, reset poisoning)
- Privilege escalation via mass assignment or policy gaps
- Tenant data disclosure (IDOR, debug, SQL)
- RCE via unserialize/queue gadgets or webroot upload

## Pro Tips

1. `composer.lock` Laravel version → known CVEs (Ignition RCE era, etc.) then confirm the patch is actually present
2. `APP_KEY` in `.env` committed or leaked in debug is a full session-forge finding, not "info"
3. Treat Livewire public props as an unauthenticated API
4. Combine mass assignment with IDOR: change `organization_id` on your own object
5. Queue + file + unserialize is how Laravel RCEs actually land — follow the job payload, not just HTTP
