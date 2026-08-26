"""Tests that run_strix_scan bootstraps a global ReportState for library
callers that never registered one themselves (unlike the CLI/TUI, which
call set_global_report_state() before invoking the runner) — otherwise
every create_vulnerability_report/finish_scan call silently no-ops and a
scan that genuinely found issues is reported with zero findings.
"""

from __future__ import annotations

import json
import types
from typing import Any

import pytest
from agents import ModelSettings

import strix.report.state as report_state_module
import strix.tools.notes.tools as notes_tools
import strix.tools.todo.tools as todo_tools
from strix.core import runner
from strix.report.state import get_global_report_state, set_global_report_state
from strix.runtime import session_manager


def _wire_runner(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    monkeypatch.setattr(runner, "run_dir_for", lambda _scan_id: tmp_path)
    monkeypatch.setattr(report_state_module, "run_dir_for", lambda _scan_id: tmp_path)
    monkeypatch.setattr(runner, "runtime_state_dir", lambda _run_dir: tmp_path)
    monkeypatch.setattr(runner, "setup_scan_logging", lambda _run_dir: lambda: None)
    monkeypatch.setattr(runner, "set_scan_id", lambda _scan_id: None)

    settings = types.SimpleNamespace(
        llm=types.SimpleNamespace(
            model="openai/gpt-4o",
            reasoning_effort="high",
            force_required_tool_choice=False,
            timeout=300,
            prompt_cache=True,
            extra_headers=None,
        ),
        runtime=types.SimpleNamespace(max_context_images=3),
    )
    monkeypatch.setattr(runner, "load_settings", lambda: settings)
    monkeypatch.setattr(runner, "configure_sdk_model_defaults", lambda _s: None)
    monkeypatch.setattr(runner, "uses_chat_completions_tool_schema", lambda _m, _s: False)
    monkeypatch.setattr(todo_tools, "hydrate_todos_from_disk", lambda _d: None)
    monkeypatch.setattr(notes_tools, "hydrate_notes_from_disk", lambda _d: None)

    async def _create_or_reuse(*_a: Any, **_k: Any) -> dict[str, Any]:
        return {"client": object(), "session": object(), "caido_client": None}

    async def _cleanup(*_a: Any, **_k: Any) -> None:
        return None

    monkeypatch.setattr(session_manager, "create_or_reuse", _create_or_reuse)
    monkeypatch.setattr(session_manager, "cleanup", _cleanup)
    monkeypatch.setattr(runner, "build_root_task", lambda _c: "task")
    monkeypatch.setattr(runner, "build_scope_context", lambda _c: "")
    monkeypatch.setattr(runner, "make_model_settings", lambda *_a, **_k: ModelSettings())
    monkeypatch.setattr(runner, "build_strix_agent", lambda **_k: object())
    monkeypatch.setattr(runner, "make_child_factory", lambda **_k: lambda **_kk: object())
    monkeypatch.setattr(runner, "open_agent_session", lambda _root_id, _db: object())


@pytest.fixture(autouse=True)
def _clean_global_report_state() -> Any:
    # Isolate from whatever any other test left registered.
    from strix.report.state import reset_global_report_state

    reset_global_report_state()
    yield
    reset_global_report_state()


@pytest.mark.asyncio
async def test_a_library_caller_gets_findings_persisted_without_registering_report_state(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    _wire_runner(monkeypatch, tmp_path)
    assert get_global_report_state() is None

    async def _agent_finds_a_bug(**_kwargs: Any) -> None:
        # Simulates what strix.tools.reporting.tool.create_vulnerability_report
        # does under the hood: look up the global report state and file
        # through it. If run_strix_scan never bootstrapped one, this would
        # be None and the finding would be silently dropped.
        rs = get_global_report_state()
        assert rs is not None, "no report state was registered for this scan"
        rs.add_vulnerability_report(title="Hardcoded secret", severity="critical")

    monkeypatch.setattr(runner, "run_agent_loop", _agent_finds_a_bug)

    await runner.run_strix_scan(
        scan_config={"targets": [], "scan_mode": "deep"},
        scan_id="scan-test",
        image="img",
    )

    vulnerabilities_path = tmp_path / "vulnerabilities.json"
    assert vulnerabilities_path.exists(), "the finding was never persisted to disk"
    findings = json.loads(vulnerabilities_path.read_text(encoding="utf-8"))
    assert len(findings) == 1
    assert findings[0]["title"] == "Hardcoded secret"

    # A single-scan-per-process library caller (e.g. a SaaS backend running
    # many scans in sequence) must not leak this scan's state into the next.
    assert get_global_report_state() is None


@pytest.mark.asyncio
async def test_a_caller_that_already_registered_report_state_keeps_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    # Mirrors the CLI/TUI, which construct and register their own
    # ReportState (with their own cleanup/atexit lifecycle) before calling
    # run_strix_scan — the runner must not touch or reset it.
    _wire_runner(monkeypatch, tmp_path)
    from strix.report.state import ReportState

    caller_owned = ReportState("scan-test")
    set_global_report_state(caller_owned)

    async def _noop(**_kwargs: Any) -> None:
        return None

    monkeypatch.setattr(runner, "run_agent_loop", _noop)

    await runner.run_strix_scan(
        scan_config={"targets": [], "scan_mode": "deep"},
        scan_id="scan-test",
        image="img",
    )

    assert get_global_report_state() is caller_owned
