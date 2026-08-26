from .conftest import otp_login
from app import crypto, models
from app.db import SessionLocal


def test_get_llm_settings_defaults(auth_client):
    client, _org = auth_client
    res = client.get("/api/settings/llm")
    assert res.status_code == 200
    body = res.json()
    assert body["model"] == ""
    assert body["api_base"] is None
    assert body["api_key_set"] is False
    assert body["api_key_last4"] is None


def test_update_llm_settings(auth_client):
    client, org = auth_client
    res = client.patch(
        "/api/settings/llm",
        json={"model": "openai/gpt-5.4", "api_base": "https://gateway.example.com/v1", "api_key": "sk-test-abcd1234"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["model"] == "openai/gpt-5.4"
    assert body["api_base"] == "https://gateway.example.com/v1"
    assert body["api_key_set"] is True
    assert body["api_key_last4"] == "1234"

    # Persisted: a fresh GET reflects the same values.
    refetched = client.get("/api/settings/llm").json()
    assert refetched["model"] == "openai/gpt-5.4"
    assert refetched["api_key_last4"] == "1234"

    db = SessionLocal()
    try:
        row = db.get(models.OrgLlmSettings, org["id"])
        assert row.api_key != "sk-test-abcd1234"
        assert crypto.decrypt(row.api_key) == "sk-test-abcd1234"
    finally:
        db.close()


def test_update_llm_settings_omitting_api_key_leaves_it_unchanged(auth_client):
    client, _org = auth_client
    client.patch("/api/settings/llm", json={"model": "openai/gpt-5.4", "api_key": "sk-original"})
    res = client.patch("/api/settings/llm", json={"model": "openai/gpt-5-mini"})
    body = res.json()
    assert body["model"] == "openai/gpt-5-mini"
    assert body["api_key_set"] is True
    assert body["api_key_last4"] == "inal"


def test_clear_api_key(auth_client):
    client, _org = auth_client
    client.patch("/api/settings/llm", json={"api_key": "sk-original"})
    res = client.patch("/api/settings/llm", json={"clear_api_key": True})
    body = res.json()
    assert body["api_key_set"] is False
    assert body["api_key_last4"] is None


def test_update_llm_settings_requires_admin(auth_client):
    client, org = auth_client
    invite = client.post("/api/members/invitations", json={"email": "plain@example.com", "role": "member"})
    token = invite.json()["dev_accept_token"]

    otp_login(client, "plain@example.com")
    client.post("/api/members/invitations/accept", json={"token": token})
    client.post("/api/auth/switch-org", json={"org_id": org["id"]})

    res = client.patch("/api/settings/llm", json={"model": "openai/gpt-5.4"})
    assert res.status_code == 403
    assert res.json()["detail"] == "admin_required"

    # Non-admins can still read.
    assert client.get("/api/settings/llm").status_code == 200


def test_blank_api_base_clears_it(auth_client):
    client, _org = auth_client
    client.patch("/api/settings/llm", json={"api_base": "https://gateway.example.com/v1"})
    res = client.patch("/api/settings/llm", json={"api_base": "   "})
    assert res.json()["api_base"] is None
