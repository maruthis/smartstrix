from .conftest import otp_login
from app import crypto, models
from app.db import SessionLocal
from app.llm_probe import LlmConnectionError
from app.routers import llm_settings as llm_router


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


def test_validate_llm_settings_success(auth_client, monkeypatch):
    monkeypatch.setattr(llm_router, "probe_llm_connection", lambda **_kwargs: None)
    client, _org = auth_client
    res = client.post(
        "/api/settings/llm/validate",
        json={
            "model": "accounts/fireworks/models/kimi-k2p6",
            "api_base": "https://api.fireworks.ai/inference/v1",
            "api_key": "fw-test",
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert "Connection verified" in body["message"]


def test_validate_llm_settings_uses_stored_key(auth_client, monkeypatch):
    seen: dict[str, str | None] = {}

    def _capture(*, model: str, api_key: str, api_base: str | None) -> None:
        seen["model"] = model
        seen["api_key"] = api_key
        seen["api_base"] = api_base

    monkeypatch.setattr(llm_router, "probe_llm_connection", _capture)
    client, _org = auth_client
    client.patch("/api/settings/llm", json={"api_key": "sk-stored-key"})
    res = client.post("/api/settings/llm/validate", json={"model": "openai/gpt-5.4"})
    assert res.status_code == 200
    assert seen["api_key"] == "sk-stored-key"
    assert seen["model"] == "openai/gpt-5.4"


def test_validate_llm_settings_rejects_missing_model(auth_client):
    client, _org = auth_client
    res = client.post("/api/settings/llm/validate", json={"model": "  ", "api_key": "sk-test"})
    assert res.status_code == 400
    assert res.json()["detail"] == "Enter a model name to verify the connection."


def test_validate_llm_settings_rejects_missing_key(auth_client):
    client, _org = auth_client
    res = client.post("/api/settings/llm/validate", json={"model": "openai/gpt-5.4"})
    assert res.status_code == 400
    assert res.json()["detail"] == "Enter an API key to verify this provider."


def test_validate_llm_settings_returns_business_error(auth_client, monkeypatch):
    def _fail(**_kwargs: object) -> None:
        raise LlmConnectionError("The API key was rejected. Check the key and try again.")

    monkeypatch.setattr(llm_router, "probe_llm_connection", _fail)
    client, _org = auth_client
    res = client.post(
        "/api/settings/llm/validate",
        json={"model": "openai/gpt-5.4", "api_key": "sk-bad"},
    )
    assert res.status_code == 400
    assert res.json()["detail"] == "The API key was rejected. Check the key and try again."


def test_validate_llm_settings_requires_admin(auth_client, monkeypatch):
    monkeypatch.setattr(llm_router, "probe_llm_connection", lambda **_kwargs: None)
    client, org = auth_client
    invite = client.post("/api/members/invitations", json={"email": "plain@example.com", "role": "member"})
    token = invite.json()["dev_accept_token"]
    otp_login(client, "plain@example.com")
    client.post("/api/members/invitations/accept", json={"token": token})
    client.post("/api/auth/switch-org", json={"org_id": org["id"]})

    res = client.post("/api/settings/llm/validate", json={"model": "openai/gpt-5.4", "api_key": "sk-test"})
    assert res.status_code == 403
    assert res.json()["detail"] == "admin_required"
