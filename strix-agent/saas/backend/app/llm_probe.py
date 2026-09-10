"""Live LLM-provider probe used by org LLM settings validation."""

from __future__ import annotations

import logging
from urllib.parse import urlparse

import httpx


logger = logging.getLogger(__name__)

_PROBE_TIMEOUT_S = 60.0
_PROBE_MAX_TOKENS = 16


class LlmConnectionError(Exception):
    """Raised with a customer-facing message when the provider cannot be reached."""


def _litellm_completion() -> object | None:
    try:
        from litellm import completion  # noqa: PLC0415
    except ImportError:
        return None
    return completion


def probe_llm_connection(*, model: str, api_key: str, api_base: str | None) -> None:
    """Send a tiny completion to confirm model, key, and optional base URL.

    Custom API bases are probed as OpenAI-compatible HTTP so LiteLLM's
    provider routing cannot send the request to the wrong host. Without a
    base URL, LiteLLM is used when installed (same routing as scans).
    """
    if api_base:
        _probe_openai_compatible(model=model, api_key=api_key, api_base=api_base)
        return

    litellm_completion = _litellm_completion()
    if litellm_completion is None:
        _probe_openai_compatible(model=model, api_key=api_key, api_base=api_base)
        return

    try:
        litellm_completion(
            model=model,
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=_PROBE_MAX_TOKENS,
            timeout=_PROBE_TIMEOUT_S,
            api_key=api_key,
        )
    except Exception as exc:
        logger.info("LLM probe via LiteLLM failed: %s", exc)
        raise LlmConnectionError(friendly_llm_error(exc)) from exc


def _chat_completions_url(api_base: str | None) -> str:
    base = (api_base or "https://api.openai.com/v1").rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    path = urlparse(base).path
    if path in ("", "/"):
        return f"{base}/v1/chat/completions"
    return f"{base}/chat/completions"


def _candidate_chat_urls(api_base: str | None) -> list[str]:
    primary = _chat_completions_url(api_base)
    urls = [primary]
    if api_base and urlparse(api_base.rstrip("/")).path in ("", "/"):
        alt = f"{api_base.rstrip('/')}/chat/completions"
        if alt not in urls:
            urls.append(alt)
    return urls


def _probe_openai_compatible(*, model: str, api_key: str, api_base: str | None) -> None:
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": _PROBE_MAX_TOKENS,
    }
    headers = {
        "authorization": f"Bearer {api_key}",
        "content-type": "application/json",
    }
    urls = _candidate_chat_urls(api_base)
    try:
        with httpx.Client(timeout=_PROBE_TIMEOUT_S, follow_redirects=True) as client:
            for index, url in enumerate(urls):
                try:
                    response = client.post(url, headers=headers, json=payload)
                    response.raise_for_status()
                    return
                except httpx.HTTPStatusError as exc:
                    is_last = index == len(urls) - 1
                    if not is_last and exc.response is not None and exc.response.status_code == 404:
                        continue
                    raise
    except Exception as exc:
        logger.info("LLM probe via HTTP failed: %s", exc)
        raise LlmConnectionError(friendly_llm_error(exc)) from exc


def _status_code(exc: BaseException) -> int | None:
    for attr in ("status_code", "status"):
        value = getattr(exc, attr, None)
        if isinstance(value, int):
            return value
    response = getattr(exc, "response", None)
    if response is not None:
        code = getattr(response, "status_code", None)
        if isinstance(code, int):
            return code
    return None


def _exception_text(exc: BaseException) -> str:
    parts = [str(exc)]
    response = getattr(exc, "response", None)
    if response is not None:
        try:
            parts.append(response.text or "")
        except Exception:
            pass
    return " ".join(parts).lower()


def friendly_llm_error(exc: BaseException) -> str:
    """Map provider/SDK failures to a short, non-technical message."""
    code = _status_code(exc)
    text = _exception_text(exc)
    name = type(exc).__name__.lower()
    unauthorized = (
        "invalid api key" in text
        or "unauthorized" in text
        or "authentication" in text
        or "auth_error" in text
        or "no api key" in text
    )
    missing = "not found" in text or "does not exist" in text or "invalid model" in text
    limited = "rate limit" in text or "too many requests" in text
    ssl_failed = "certificate" in text or "ssl" in name or "ssl" in text

    if isinstance(exc, httpx.TimeoutException) or "timeout" in name:
        return "The provider didn't respond in time. Check the API base URL and try again."
    if ssl_failed:
        return "We couldn't establish a trusted connection to the provider. Check the API base URL."
    if isinstance(exc, httpx.RequestError) or "connect" in name:
        return "We couldn't reach the provider. Check the API base URL and your network connection."
    if code in {401, 403} or unauthorized:
        return "The API key was rejected. Check the key and try again."
    if code == 404 or missing:
        return "The model or endpoint could not be found. Check the model name and API base URL."
    if code == 429 or limited:
        return "The provider is rate-limiting this key. Wait a moment and try again."
    if code is not None and code >= 500:
        return "The provider is unavailable right now. Try again in a few minutes."
    return "We couldn't verify this provider. Check the model, API base URL, and API key."
