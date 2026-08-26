"""Billing integration behind a provider interface.

`MockBillingProvider` is the default — "adding a card" just flips a flag on
the org's `Subscription` row and clears the trial banner, no payment
processor involved. `RealStripeProvider` activates once
`SAAS_STRIPE_SECRET_KEY` is set; it's a scaffold for Stripe Checkout/Billing
Portal + webhook handling, which needs a real Stripe account and product/
price IDs only the operator can create.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from ..settings import settings


class BillingProvider(ABC):
    @abstractmethod
    def create_setup_intent(self, *, org_id: str) -> dict[str, Any]:
        """Start a card-collection flow; mock returns a fake client secret."""

    @abstractmethod
    def attach_card(self, *, org_id: str) -> dict[str, Any]:
        """Mark that a card has been attached (mock: instantly; real: via webhook)."""

    @abstractmethod
    def list_invoices(self, *, org_id: str) -> list[dict[str, Any]]:
        """Invoice history for the billing settings page."""


class MockBillingProvider(BillingProvider):
    def create_setup_intent(self, *, org_id: str) -> dict[str, Any]:
        return {"mock": True, "client_secret": f"mock_secret_{org_id}"}

    def attach_card(self, *, org_id: str) -> dict[str, Any]:
        return {"mock": True, "card_added": True}

    def list_invoices(self, *, org_id: str) -> list[dict[str, Any]]:
        return []


class RealStripeProvider(BillingProvider):
    """Scaffold for a real Stripe integration.

    Fill in with the `stripe` SDK: Checkout Session or SetupIntent creation,
    a `/api/webhooks/stripe` handler verified via
    `settings.stripe_webhook_secret`, and Billing Portal session links for
    the invoices list. Requires `settings.stripe_secret_key`.
    """

    def create_setup_intent(self, *, org_id: str) -> dict[str, Any]:
        raise NotImplementedError("Real Stripe integration not yet implemented; see class docstring.")

    def attach_card(self, *, org_id: str) -> dict[str, Any]:
        raise NotImplementedError

    def list_invoices(self, *, org_id: str) -> list[dict[str, Any]]:
        raise NotImplementedError


def get_billing_provider() -> BillingProvider:
    if settings.billing_configured:
        return RealStripeProvider()
    return MockBillingProvider()
