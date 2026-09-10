from __future__ import annotations

import httpx
import pytest

from app.llm_probe import (
    LlmConnectionError,
    _chat_completions_url,
    friendly_llm_error,
    probe_llm_connection,
)


def test_chat_completions_url_appends_path() -> None:
    assert _chat_completions_url(None) == "https://api.openai.com/v1/chat/completions"
    assert _chat_completions_url("https://gw.example/v1/") == "https://gw.example/v1/chat/completions"
    assert (
        _chat_completions_url("https://gw.example/v1/chat/completions")
        == "https://gw.example/v1/chat/completions"
    )
    assert _chat_completions_url("https://llm.example.com") == "https://llm.example.com/v1/chat/completions"


@pytest.mark.parametrize(
    ("exc", "snippet"),
    [
        (httpx.TimeoutException("timed out"), "didn't respond in time"),
        (httpx.ConnectError("refused"), "couldn't reach the provider"),
        (Exception("Invalid API key"), "API key was rejected"),
        (Exception('{"error":{"message":"Authentication Error","type":"auth_error"}}'), "API key was rejected"),
        (Exception("model not found"), "could not be found"),
        (Exception("Invalid model name passed"), "could not be found"),
        (Exception("Rate limit exceeded"), "rate-limiting"),
        (Exception("something else"), "couldn't verify this provider"),
    ],
)
def test_friendly_llm_error_maps_known_failures(exc: BaseException, snippet: str) -> None:
    assert snippet in friendly_llm_error(exc)


def test_friendly_llm_error_uses_http_status() -> None:
    request = httpx.Request("POST", "https://example.com/v1/chat/completions")
    response = httpx.Response(401, request=request)
    exc = httpx.HTTPStatusError("auth", request=request, response=response)
    assert "API key was rejected" in friendly_llm_error(exc)

    response_404 = httpx.Response(404, request=request)
    missing = httpx.HTTPStatusError("missing", request=request, response=response_404)
    assert "could not be found" in friendly_llm_error(missing)

    response_429 = httpx.Response(429, request=request)
    limited = httpx.HTTPStatusError("slow", request=request, response=response_429)
    assert "rate-limiting" in friendly_llm_error(limited)

    response_500 = httpx.Response(503, request=request)
    unavailable = httpx.HTTPStatusError("down", request=request, response=response_500)
    assert "unavailable right now" in friendly_llm_error(unavailable)


def test_probe_uses_litellm_when_available(monkeypatch) -> None:
    seen: dict[str, object] = {}

    def fake_completion(**kwargs: object) -> dict[str, object]:
        seen.update(kwargs)
        return {"choices": []}

    monkeypatch.setattr("app.llm_probe._litellm_completion", lambda: fake_completion)
    probe_llm_connection(model="openai/gpt-5.4", api_key="sk-test", api_base=None)
    assert seen["model"] == "openai/gpt-5.4"
    assert seen["api_key"] == "sk-test"
    assert "api_base" not in seen


def test_probe_maps_litellm_failure(monkeypatch) -> None:
    def fake_completion(**_kwargs: object) -> None:
        raise RuntimeError("Invalid API key")

    monkeypatch.setattr("app.llm_probe._litellm_completion", lambda: fake_completion)
    with pytest.raises(LlmConnectionError, match="API key was rejected"):
        probe_llm_connection(model="openai/gpt-5.4", api_key="bad", api_base=None)


def test_probe_uses_http_fallback_when_litellm_missing(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class _Response:
        def raise_for_status(self) -> None:
            return None

    class _Client:
        def __init__(self, timeout: float, **_kwargs: object) -> None:
            captured["timeout"] = timeout

        def __enter__(self) -> _Client:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def post(self, url: str, headers: dict[str, str], json: dict[str, object]) -> _Response:
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            return _Response()

    monkeypatch.setattr("app.llm_probe.httpx.Client", _Client)
    monkeypatch.setattr("app.llm_probe._litellm_completion", lambda: None)

    probe_llm_connection(
        model="accounts/fireworks/models/kimi-k2p6",
        api_key="fw-secret",
        api_base="https://api.fireworks.ai/inference/v1",
    )

    assert captured["url"] == "https://api.fireworks.ai/inference/v1/chat/completions"
    assert captured["headers"]["authorization"] == "Bearer fw-secret"
    assert captured["json"]["model"] == "accounts/fireworks/models/kimi-k2p6"


def test_probe_uses_v1_path_for_origin_api_base(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class _Response:
        def raise_for_status(self) -> None:
            return None

    class _Client:
        def __init__(self, timeout: float, **_kwargs: object) -> None:
            captured["timeout"] = timeout
            del _kwargs

        def __enter__(self) -> _Client:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def post(self, url: str, headers: dict[str, str], json: dict[str, object]) -> _Response:
            captured.setdefault("urls", [])
            captured["urls"].append(url)  # type: ignore[union-attr]
            captured["headers"] = headers
            captured["json"] = json
            return _Response()

    monkeypatch.setattr("app.llm_probe.httpx.Client", _Client)
    monkeypatch.setattr("app.llm_probe._litellm_completion", lambda: None)

    probe_llm_connection(
        model="fireworks_ai/accounts/fireworks/models/gpt-oss-120b",
        api_key="sk-test",
        api_base="https://llm.example.com",
    )

    assert captured["urls"] == ["https://llm.example.com/v1/chat/completions"]
    assert captured["json"]["model"] == "fireworks_ai/accounts/fireworks/models/gpt-oss-120b"


def test_probe_raises_customer_message_on_http_error(monkeypatch) -> None:
    request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    response = httpx.Response(401, request=request)

    class _Client:
        def __init__(self, timeout: float, **_kwargs: object) -> None:
            del timeout, _kwargs

        def __enter__(self) -> _Client:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def post(self, *_args: object, **_kwargs: object) -> httpx.Response:
            raise httpx.HTTPStatusError("nope", request=request, response=response)

    monkeypatch.setattr("app.llm_probe.httpx.Client", _Client)
    monkeypatch.setattr("app.llm_probe._litellm_completion", lambda: None)

    with pytest.raises(LlmConnectionError, match="API key was rejected"):
        probe_llm_connection(model="openai/gpt-5.4", api_key="bad", api_base=None)
