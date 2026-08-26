---
name: wordpress
description: Security testing playbook for WordPress core, plugins, and themes covering authz, REST/AJAX, unserialize, file upload, and XML-RPC
---

# WordPress

Security testing for WordPress sites and plugin/theme code. Focus on capability/nonce gaps, privileged AJAX and REST routes, PHP object injection, file upload to RCE, and leftover install/debug surfaces — not generic PHP SQLi (use `sql_injection` / `laravel` when the stack is Laravel).

## Attack Surface

**Core**
- `/wp-login.php`, `/wp-admin/`, `/xmlrpc.php`, `/wp-cron.php`
- REST: `/wp-json/wp/v2/`, custom namespaces
- Uploads: `/wp-content/uploads/`, `admin-ajax.php` / `async-upload.php`

**Plugins / themes**
- `wp-content/plugins/*`, `wp-content/themes/*`
- Shortcodes, Gutenberg blocks, WP-CLI commands
- Settings APIs, options.php, transients

**Data**
- `unserialize` / `maybe_unserialize` on user or HTTP input
- `$wpdb->query` with unprepared interpolation
- `update_user_meta` / `update_option` from request fields

## High-Value Targets

- `/wp-admin/install.php` or installer still reachable
- Plugin AJAX (`admin-ajax.php?action=`) registered for `wp_ajax_nopriv_*`
- REST routes with `permission_callback => '__return_true'`
- File managers, backup, newsletter, membership, WooCommerce checkout/payment plugins
- `xmlrpc.php` system.multicall brute force / pingback SSRF
- Debug: `WP_DEBUG_LOG`, `phpinfo` in plugins, backup zips in uploads
- User enumeration: `?author=1`, REST `/wp-json/wp/v2/users`

## Reconnaissance

```
GET /wp-json/          (route catalog)
GET /wp-json/wp/v2/users
GET /xmlrpc.php
GET /wp-content/plugins/<slug>/readme.txt  (version)
wp-config.php.bak  debug.log  *.zip in uploads
```

White-box:

```
register_rest_route
wp_ajax_nopriv_
permission_callback
check_ajax_referer  current_user_can
unserialize(  maybe_unserialize(
$_GET  $_POST  $_REQUEST
move_uploaded_file  WP_Filesystem
```

## Key Vulnerabilities

### Missing capability / nonce

- Admin actions callable as subscriber/author (`current_user_can` missing or wrong cap)
- REST `permission_callback` always true or only `is_user_logged_in`
- CSRF: state change without `check_admin_referer` / `wp_verify_nonce`
- IDOR on `user_id` / `post_id` / `order_id` in AJAX after a weak cap check (`read` instead of `edit_post`)

### Unserialize / object injection

- `unserialize($_GET['data'])`, cookies, import files, widget settings
- Phar + polyglot uploads if `unserialize` is invoked on a filename
- Pair with `insecure_deserialization`

### SQL / XSS / include

- `$wpdb->query("... $_GET[id]")` vs `$wpdb->prepare`
- Stored XSS in post meta, options, unsanitized `echo` in admin/settings (admin XSS → add admin)
- `include $_GET['file']`, `download.php?file=` path traversal
- Shortcodes that echo unsanitized attributes

### Files and RCE

- Upload of `.php` via media, plugin "custom CSS/PHP", or MIME bypass (`image/jpeg` + `.php`)
- Writable `wp-content` from the web user; plugin/theme editor enabled for low-priv users
- `update_option('siteurl')` / `admin_email` takeover

### XML-RPC / auth

- `xmlrpc.php` enabled: brute force amplification, pingback SSRF (`ssrf`)
- Weak `COOKIEHASH` / leaked `AUTH_KEY` in `wp-config.php` (webroot backup)
- Password reset host header poisoning if `$_SERVER['HTTP_HOST']` is trusted

## Testing Methodology

1. Fingerprint core + every plugin version; map public REST and `nopriv` AJAX
2. Auth as subscriber and author; replay admin AJAX/REST
3. Fuzz plugin settings and import endpoints for unserialize and file include
4. Upload polyglots; check execution under uploads (server mapping)
5. WooCommerce/payment plugins: tamper totals (pair `stripe` / `business_logic`)
6. Confirm xmlrpc and user enum only if they enable a further attack (credential stuffing, IDOR)

## Validation

- Privilege change, stored XSS in another user, file read/write outside uploads, or code exec
- User enumeration alone is informational unless combined with weak passwords you are authorized to test
- Out-of-date plugin version is not a finding without a reachable exploit path (CVE + check the code is unpatched)

## False Positives

- `wp_ajax_` (authenticated) actions that correctly `current_user_can('manage_options')`
- REST routes that are meant to be public (posts already public)
- `unserialize` of an option written only by `manage_options` with a nonce

## Impact

- Site takeover (admin XSS, option update, upload RCE)
- WooCommerce order/PII disclosure
- SSRF via pingback or plugin fetchers
- Persistence via plugin dropper

## Pro Tips

1. `readme.txt` Stable tag vs the PHP files actually deployed — they often disagree
2. `nopriv` is the first grep; the second is REST `permission_callback`
3. Admin XSS in WordPress is typically RCE (plugin install / theme editor / file PHP)
4. Pair with `insecure_file_uploads`, `csrf`, `ssrf`, and `exploitability_triage`
5. Multisite: `grant_super_admin` and unfiltered HTML for untrusted roles
