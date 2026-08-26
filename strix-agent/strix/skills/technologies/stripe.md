---
name: stripe
description: Security testing for Stripe integrations covering webhook authenticity, amount tampering, idempotency, race refunds, and secret leakage
---

# Stripe

Testing applications that take payments through Stripe (Checkout, PaymentIntents, Billing, Connect, Identity). The API is usually solid; the bug is almost always **your** webhook handler, price trust, or race on credits. Pair with `business_logic`.

## Attack Surface

**Client → your API**
- Create-session / create-intent endpoints that accept `amount`, `price_id`, `quantity`, `currency`, `metadata`
- Success URLs and client-only "payment complete" flags
- Customer portal / billing-portal session creation (`customer` id)

**Stripe → your API**
- Webhooks: `/webhooks/stripe`, `/api/stripe/webhook`
- Events: `checkout.session.completed`, `invoice.paid`, `customer.subscription.*`, `charge.refunded`, `account.updated` (Connect)

**Secrets**
- `sk_live_`, `sk_test_`, `whsec_`, restricted keys in frontend, mobile, Git, CI
- Stripe CLI / Dashboard webhook signing secrets

## High-Value Targets

- Webhook route with no `Stripe-Signature` verification (or verify skipped if header missing)
- Entitlement granted in the **success URL handler** instead of the webhook
- `amount` / `unit_amount` taken from the client when creating a PaymentIntent
- Idempotency keys attacker-controlled and reused across users
- Connect: platform webhook trusting `account` without checking the connected account id
- Race: double-credit on two `checkout.session.completed` deliveries

## Reconnaissance

```
sk_live  sk_test  whsec_  stripe.webhooks.constructEvent
checkout.sessions.create  paymentIntents.create
metadata  success_url  client_reference_id
```

Map: which Stripe objects you create, which events you handle, where credits/roles are written.

## Key Vulnerabilities

### Webhook authenticity

- No signature check; attacker POSTs `checkout.session.completed` with their `client_reference_id` as a victim and a $1 session they paid
- Using the **test** signing secret in production (or vice versa)
- `tolerance` so large that replay of old events re-grants entitlements
- CSRF on a GET webhook (rare but exists)

Prove: unsigned or wrong-secret body is accepted **or** a replay credits twice. Do not send events to Stripe's production for out-of-scope accounts.

### Amount / price trust

- Client sends `amount: 100` (cents) while UI showed $100.00
- `price_id` of a $1 test price accepted for a premium SKU
- Quantity / coupon / trial_end set by the client without server allowlists
- Changing `metadata.user_id` on the session to another account

Server must look up price from **your** catalog and bind the session to the authenticated user.

### Success-URL race

- Granting access in `GET /success?session_id=` by retrieving the session but not checking `payment_status` / `status`
- User stops at success URL without paying; or pays then hits success twice for double SKU

Source of truth is the webhook (or a server-side retrieve **plus** paid status) with an idempotent grant.

### Idempotency and Connect

- Stripe retries webhooks; handler that `INSERT credit` without unique `(event.id)` double-spends
- Refund/void vs grant order: refund event ignored → user keeps the good
- Connect: processing events for a different connected account; transferring to attacker `stripe_account`

### Secret leakage

- `sk_live` in SPA, Android APK, Git history, support tickets
- Restricted keys with `rak_live_` that can still read customers or write charges
- Webhook URL on a debug endpoint that dumps raw bodies (cards in logs — PCI)

## Testing Methodology

1. Inventory every Stripe call and every event handler
2. Create a **test-mode** session (authorized target) and tamper amount/price/metadata
3. Replay webhook bodies with and without valid signatures
4. Hit success URL before payment and twice after
5. Parallel two webhooks with the same `id` and two with different ids same session
6. Search source + history for live secrets (file via secrets workflow; rotate, do not use them)

## Validation

- Unauthorized entitlement, wrong amount captured (in test mode), or cross-account grant
- Unsigned webhook accepted
- Double credit with evidence (two ledger rows)
- Live key in a public artifact is a secret finding even without a payment PoC

## False Positives

- Test keys in documented sandbox-only configs
- Signature verification that rejects missing headers
- Amount field on the client that the server ignores in favor of `price_id` from the DB

## Impact

- Stolen goods/subscriptions (pay $1, get premium)
- Cross-tenant billing and PII (Connect / customer objects)
- PCI and account takeover via leaked `sk_live`
- Drain via refund/credit races

## Pro Tips

1. Stripe's own API is not the target — your mapping from events to entitlements is
2. `metadata` is not authenticated against the user unless you set it server-side after auth
3. Pair with `race_conditions`, `idor`, and `exploitability_triage`
4. Idempotency keys on **your** grant table should be Stripe `event.id`, not the client's key
5. Checkout `client_reference_id` is attacker-controlled if the client is allowed to set it
