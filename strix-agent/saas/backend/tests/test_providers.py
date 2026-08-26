import hashlib
import hmac

import pytest

from app.providers.billing import MockBillingProvider, RealStripeProvider, get_billing_provider
from app.providers.github import MockGitHubProvider, RealGitHubProvider, get_github_provider


def test_mock_github_provider_methods():
    provider = MockGitHubProvider()
    assert len(provider.installable_repositories()) == 3
    assert provider.create_check_run(full_name="a/b", pr_number=1, conclusion="success", summary="ok")["mock"] is True
    assert provider.post_pr_comment(full_name="a/b", pr_number=1, body="hi")["mock"] is True
    assert provider.verify_webhook_signature(payload=b"{}", signature_header=None) is True


def test_get_github_provider_defaults_to_mock():
    assert isinstance(get_github_provider(), MockGitHubProvider)


def test_get_github_provider_returns_real_when_configured(monkeypatch):
    from app.settings import settings

    monkeypatch.setattr(settings, "github_app_id", "id")
    monkeypatch.setattr(settings, "github_app_private_key", "key")
    assert isinstance(get_github_provider(), RealGitHubProvider)


def test_real_github_provider_signature_verification(monkeypatch):
    from app.settings import settings

    monkeypatch.setattr(settings, "github_webhook_secret", "topsecret")
    provider = RealGitHubProvider()
    payload = b'{"hello":"world"}'

    correct = "sha256=" + hmac.new(b"topsecret", payload, hashlib.sha256).hexdigest()
    assert provider.verify_webhook_signature(payload=payload, signature_header=correct) is True
    assert provider.verify_webhook_signature(payload=payload, signature_header="sha256=deadbeef") is False
    assert provider.verify_webhook_signature(payload=payload, signature_header="not-sha256=x") is False
    assert provider.verify_webhook_signature(payload=payload, signature_header=None) is False


def test_real_github_provider_unimplemented_methods_raise():
    provider = RealGitHubProvider()
    with pytest.raises(NotImplementedError):
        provider.installable_repositories()
    with pytest.raises(NotImplementedError):
        provider.create_check_run(full_name="a/b", pr_number=1, conclusion="success", summary="x")
    with pytest.raises(NotImplementedError):
        provider.post_pr_comment(full_name="a/b", pr_number=1, body="x")


def test_mock_billing_provider_methods():
    provider = MockBillingProvider()
    assert provider.create_setup_intent(org_id="org1")["mock"] is True
    assert provider.attach_card(org_id="org1")["card_added"] is True
    assert provider.list_invoices(org_id="org1") == []


def test_get_billing_provider_defaults_to_mock():
    assert isinstance(get_billing_provider(), MockBillingProvider)


def test_get_billing_provider_returns_real_when_configured(monkeypatch):
    from app.settings import settings

    monkeypatch.setattr(settings, "stripe_secret_key", "sk_test_123")
    assert isinstance(get_billing_provider(), RealStripeProvider)


def test_real_stripe_provider_unimplemented_methods_raise():
    provider = RealStripeProvider()
    with pytest.raises(NotImplementedError):
        provider.create_setup_intent(org_id="org1")
    with pytest.raises(NotImplementedError):
        provider.attach_card(org_id="org1")
    with pytest.raises(NotImplementedError):
        provider.list_invoices(org_id="org1")
