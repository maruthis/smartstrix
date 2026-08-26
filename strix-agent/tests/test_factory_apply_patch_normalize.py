"""Tests for apply_patch input normalization in strix.agents.factory.

The SDK's apply_patch parser requires the raw text to start with exactly
'*** Begin Patch' and end with '*** End Patch' (agents/sandbox/capabilities/
tools/apply_patch_tool.py's _parse_apply_patch_input does a strict
lines[0] != _BEGIN_PATCH check). A model wrapping an otherwise well-formed
patch in a markdown code fence, or prefixing it with a sentence of
commentary, fails that check even though the patch content itself is
fine. _normalize_apply_patch_input recovers from both cases before the
input reaches the SDK parser."""

from __future__ import annotations

import json
from typing import Any

import pytest
from agents.tool import CustomTool
from agents.tool_context import ToolContext

from strix.agents import factory


VALID_PATCH = "*** Begin Patch\n*** Add File: hello.txt\n+Hello world\n*** End Patch"


def test_leaves_an_already_correct_patch_unchanged() -> None:
    assert factory._normalize_apply_patch_input(VALID_PATCH) == VALID_PATCH


def test_strips_surrounding_whitespace() -> None:
    assert factory._normalize_apply_patch_input(f"\n\n  {VALID_PATCH}  \n\n") == VALID_PATCH


def test_strips_a_wrapping_markdown_code_fence() -> None:
    fenced = f"```patch\n{VALID_PATCH}\n```"
    assert factory._normalize_apply_patch_input(fenced) == VALID_PATCH


def test_strips_a_bare_code_fence_with_no_language_tag() -> None:
    fenced = f"```\n{VALID_PATCH}\n```"
    assert factory._normalize_apply_patch_input(fenced) == VALID_PATCH


def test_strips_leading_commentary_before_the_begin_marker() -> None:
    prefixed = f"Here is the patch:\n\n{VALID_PATCH}"
    assert factory._normalize_apply_patch_input(prefixed) == VALID_PATCH


def test_strips_trailing_commentary_after_the_end_marker() -> None:
    suffixed = f"{VALID_PATCH}\n\nLet me know if you need anything else."
    assert factory._normalize_apply_patch_input(suffixed) == VALID_PATCH


def test_strips_both_leading_and_trailing_commentary_and_a_fence() -> None:
    wrapped = f"Sure, here's the diff:\n```\n{VALID_PATCH}\n```\nDone."
    assert factory._normalize_apply_patch_input(wrapped) == VALID_PATCH


def test_leaves_input_without_both_markers_untouched() -> None:
    """No recoverable envelope — leave it as-is so the SDK's own clear
    error ("must start with '*** Begin Patch'") still fires."""
    garbage = "just some text with no patch markers at all"
    assert factory._normalize_apply_patch_input(garbage) == garbage


def test_leaves_input_missing_the_end_marker_untouched() -> None:
    truncated = "*** Begin Patch\n*** Add File: hello.txt\n+Hello world"
    assert factory._normalize_apply_patch_input(truncated) == truncated.strip()


@pytest.mark.asyncio
async def test_wired_invoke_normalizes_before_calling_the_sdk_tool() -> None:
    received: dict[str, str] = {}

    async def _fake_on_invoke_tool(_ctx: Any, custom_input: str) -> str:
        received["custom_input"] = custom_input
        return "applied"

    tool = CustomTool(
        name="apply_patch",
        description="apply_patch tool",
        on_invoke_tool=_fake_on_invoke_tool,
    )
    wrapped = factory._custom_tool_as_function_tool(tool)

    ctx = ToolContext(context={}, tool_name="apply_patch", tool_call_id="c1", tool_arguments="{}")
    fenced = f"```patch\n{VALID_PATCH}\n```"
    result = await wrapped.on_invoke_tool(ctx, json.dumps({"patch": fenced}))

    assert received["custom_input"] == VALID_PATCH
    assert result == "applied"


@pytest.mark.asyncio
async def test_wired_invoke_still_fails_clearly_on_a_genuinely_malformed_patch() -> None:
    async def _fake_on_invoke_tool(_ctx: Any, custom_input: str) -> str:
        if not custom_input.startswith("*** Begin Patch"):
            raise ValueError("apply_patch input must start with '*** Begin Patch'")
        return "applied"

    tool = CustomTool(
        name="apply_patch",
        description="apply_patch tool",
        on_invoke_tool=_fake_on_invoke_tool,
    )
    wrapped = factory._custom_tool_as_function_tool(tool)

    ctx = ToolContext(context={}, tool_name="apply_patch", tool_call_id="c1", tool_arguments="{}")
    result = await wrapped.on_invoke_tool(ctx, json.dumps({"patch": "not a patch at all"}))

    assert "must start with" in result


@pytest.mark.asyncio
async def test_other_custom_tools_are_not_normalized() -> None:
    """The fence/commentary stripping is apply_patch-specific — a different
    custom tool's freeform input must reach the SDK byte-for-byte."""
    received: dict[str, str] = {}

    async def _fake_on_invoke_tool(_ctx: Any, custom_input: str) -> str:
        received["custom_input"] = custom_input
        return "ok"

    tool = CustomTool(
        name="some_other_tool",
        description="a different freeform tool",
        on_invoke_tool=_fake_on_invoke_tool,
    )
    wrapped = factory._custom_tool_as_function_tool(tool)

    ctx = ToolContext(
        context={}, tool_name="some_other_tool", tool_call_id="c1", tool_arguments="{}"
    )
    fenced_payload = "```\nsome raw content\n```"
    await wrapped.on_invoke_tool(ctx, json.dumps({"input": fenced_payload}))

    assert received["custom_input"] == fenced_payload
