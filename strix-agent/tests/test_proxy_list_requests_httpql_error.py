"""Tests for list_requests's HTTPQL error reporting.

Caido's "Invalid HTTPQL query" error carries a line/column that refers to
its own re-serialized query document, not the agent's httpql_filter string
— useless for the agent to act on as-is. list_requests now echoes back the
filter it actually sent plus a quoting hint on that specific error, so a
bad-syntax call is self-correctable on the next turn."""

from __future__ import annotations

import json
from typing import Any

import pytest
from agents.tool_context import ToolContext

from strix.tools.proxy import tools as proxy_tools


def _ctx(caido_client: object | None) -> ToolContext:
    return ToolContext(
        context={"caido_client": caido_client},
        tool_name="list_requests",
        tool_call_id="call-1",
        tool_arguments="{}",
    )


async def _call_list_requests(**kwargs: Any) -> dict[str, Any]:
    result: str = await proxy_tools.list_requests.on_invoke_tool(
        _ctx(object()), json.dumps(kwargs)
    )
    return json.loads(result)  # type: ignore[no-any-return]


@pytest.mark.asyncio
async def test_httpql_syntax_error_echoes_the_offending_filter_and_a_hint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _raise_invalid_httpql(*_a: Any, **_k: Any) -> Any:
        raise RuntimeError("{'message': 'Invalid HTTPQL query', 'locations': [{'line': 34}]}")

    monkeypatch.setattr(proxy_tools.caido_api, "list_requests_with_client", _raise_invalid_httpql)

    result = await _call_list_requests(httpql_filter='resp.code.eq:"200"')

    assert result["success"] is False
    assert result["httpql_filter_sent"] == 'resp.code.eq:"200"'
    assert "quot" in result["hint"].lower()


@pytest.mark.asyncio
async def test_unrelated_errors_do_not_get_the_httpql_hint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _raise_other(*_a: Any, **_k: Any) -> Any:
        raise RuntimeError("connection refused")

    monkeypatch.setattr(proxy_tools.caido_api, "list_requests_with_client", _raise_other)

    result = await _call_list_requests(httpql_filter='resp.code.eq:"200"')

    assert result["success"] is False
    assert "httpql_filter_sent" not in result
    assert "hint" not in result


@pytest.mark.asyncio
async def test_httpql_error_without_a_filter_gets_no_hint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No httpql_filter was passed, so there's nothing useful to echo back."""

    async def _raise_invalid_httpql(*_a: Any, **_k: Any) -> Any:
        raise RuntimeError("Invalid HTTPQL query")

    monkeypatch.setattr(proxy_tools.caido_api, "list_requests_with_client", _raise_invalid_httpql)

    result = await _call_list_requests()

    assert result["success"] is False
    assert "httpql_filter_sent" not in result
    assert "hint" not in result


@pytest.mark.asyncio
async def test_list_requests_without_a_client_returns_a_clean_error() -> None:
    result_json: str = await proxy_tools.list_requests.on_invoke_tool(_ctx(None), "{}")
    result = json.loads(result_json)
    assert result == {"success": False, "error": "Caido client not available in run context"}
