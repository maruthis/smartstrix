def test_billing_defaults_to_trialing(auth_client):
    client, _org = auth_client
    res = client.get("/api/settings/billing")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "trialing"
    assert body["card_added"] is False


def test_add_card_activates_subscription(auth_client):
    client, _org = auth_client
    res = client.post("/api/settings/billing/add-card")
    assert res.status_code == 200
    body = res.json()
    assert body["card_added"] is True
    assert body["status"] == "active"


def test_list_invoices_empty_in_mock_mode(auth_client):
    client, _org = auth_client
    res = client.get("/api/settings/billing/invoices")
    assert res.status_code == 200
    assert res.json() == []


def test_add_card_returns_501_when_real_provider_not_implemented(auth_client, monkeypatch):
    from app.settings import settings

    client, _org = auth_client
    monkeypatch.setattr(settings, "stripe_secret_key", "sk_test_fake")

    res = client.post("/api/settings/billing/add-card")
    assert res.status_code == 501
    assert res.json()["detail"] == "billing_provider_not_fully_configured"


def test_list_invoices_returns_501_when_real_provider_not_implemented(auth_client, monkeypatch):
    from app.settings import settings

    client, _org = auth_client
    monkeypatch.setattr(settings, "stripe_secret_key", "sk_test_fake")

    res = client.get("/api/settings/billing/invoices")
    assert res.status_code == 501
    assert res.json()["detail"] == "billing_provider_not_fully_configured"
