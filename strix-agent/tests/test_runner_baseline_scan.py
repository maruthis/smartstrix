"""Tests for run_strix_scan's Tier 3 baseline-scan wiring
(strix/core/runner.py calling strix/scan/baseline.py before the agent loop
starts) — see docs/scan-coverage-tier3-plan.md."""

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
from strix.report.state import get_global_report_state, reset_global_report_state
from strix.runtime import session_manager
from strix.scan.baseline import BaselineFinding, BaselineResult


def _settings(*, baseline_enabled: bool = True) -> types.SimpleNamespace:
    return types.SimpleNamespace(
        llm=types.SimpleNamespace(
            model="openai/gpt-4o",
            reasoning_effort="high",
            force_required_tool_choice=False,
            timeout=300,
            prompt_cache=True,
            extra_headers=None,
        ),
        runtime=types.SimpleNamespace(max_context_images=3),
        baseline=types.SimpleNamespace(enabled=baseline_enabled, timeout=180),
    )


def _wire_runner(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
    *,
    baseline_enabled: bool = True,
) -> dict[str, Any]:
    monkeypatch.setattr(runner, "run_dir_for", lambda _scan_id: tmp_path)
    monkeypatch.setattr(report_state_module, "run_dir_for", lambda _scan_id: tmp_path)
    monkeypatch.setattr(runner, "runtime_state_dir", lambda _run_dir: tmp_path)
    monkeypatch.setattr(runner, "setup_scan_logging", lambda _run_dir: lambda: None)
    monkeypatch.setattr(runner, "set_scan_id", lambda _scan_id: None)
    monkeypatch.setattr(
        runner, "load_settings", lambda: _settings(baseline_enabled=baseline_enabled)
    )
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
    monkeypatch.setattr(runner, "build_scope_context", lambda _c: {"scope": "built-in"})
    monkeypatch.setattr(runner, "make_model_settings", lambda *_a, **_k: ModelSettings())
    monkeypatch.setattr(runner, "make_child_factory", lambda **_k: lambda **_kk: object())
    monkeypatch.setattr(runner, "open_agent_session", lambda _root_id, _db: object())

    captured: dict[str, Any] = {}

    def _build_strix_agent(**kwargs: Any) -> object:
        if kwargs.get("is_root") and "kwargs" not in captured:
            captured["kwargs"] = kwargs
        return object()

    monkeypatch.setattr(runner, "build_strix_agent", _build_strix_agent)

    async def _noop(**_kwargs: Any) -> None:
        return None

    monkeypatch.setattr(runner, "run_agent_loop", _noop)
    return captured


@pytest.fixture(autouse=True)
def _clean_global_report_state() -> Any:
    reset_global_report_state()
    yield
    reset_global_report_state()


@pytest.mark.asyncio
async def test_baseline_findings_are_filed_and_persisted(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    captured = _wire_runner(monkeypatch, tmp_path)

    fake_result = BaselineResult(
        findings=[
            BaselineFinding(
                category="dependencies",
                title="CVE-2024-1234: left-pad@1.0.0",
                severity="high",
                target="package-lock.json",
                dependency_metadata={"package_name": "left-pad"},
            ),
            BaselineFinding(
                category="secrets",
                title="Secret detected (aws-key) in config.py",
                severity="high",
                target="config.py",
            ),
        ],
        raw_output={"trivy": [{"ok": True}]},
    )
    monkeypatch.setattr(runner, "run_baseline_scan", lambda *_a, **_k: fake_result)

    await runner.run_strix_scan(
        scan_config={"targets": [], "scan_mode": "deep"},
        scan_id="scan-baseline",
        image="img",
        local_sources=[{"source_path": str(tmp_path / "repo")}],
    )

    vulnerabilities_path = tmp_path / "vulnerabilities.json"
    findings = json.loads(vulnerabilities_path.read_text(encoding="utf-8"))
    assert len(findings) == 2
    sources = {f["source"] for f in findings}
    assert sources == {"baseline_scan"}
    categories = {f["coverage_category"] for f in findings}
    assert categories == {"dependencies", "secrets"}
    dep_finding = next(f for f in findings if f["coverage_category"] == "dependencies")
    assert dep_finding["finding_class"] == "dependency_cve"

    baseline_artifact = tmp_path / "baseline" / "trivy.json"
    assert baseline_artifact.exists()
    assert json.loads(baseline_artifact.read_text(encoding="utf-8")) == [{"ok": True}]

    kwargs = captured["kwargs"]
    summary = kwargs["system_prompt_context"]["baseline_scan_summary"]
    assert "1 dependency CVE" in summary
    assert "1 secret" in summary

    assert get_global_report_state() is None  # library-caller cleanup, unrelated to baseline


@pytest.mark.asyncio
async def test_baseline_scan_is_skipped_without_local_sources(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    captured = _wire_runner(monkeypatch, tmp_path)
    called = False

    def _should_not_run(*_a: Any, **_k: Any) -> BaselineResult:
        nonlocal called
        called = True
        return BaselineResult()

    monkeypatch.setattr(runner, "run_baseline_scan", _should_not_run)

    await runner.run_strix_scan(
        scan_config={"targets": [], "scan_mode": "deep"},
        scan_id="scan-no-sources",
        image="img",
    )

    assert called is False
    assert "baseline_scan_summary" not in captured["kwargs"]["system_prompt_context"]


@pytest.mark.asyncio
async def test_baseline_scan_is_skipped_when_disabled_in_settings(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    captured = _wire_runner(monkeypatch, tmp_path, baseline_enabled=False)
    called = False

    def _should_not_run(*_a: Any, **_k: Any) -> BaselineResult:
        nonlocal called
        called = True
        return BaselineResult()

    monkeypatch.setattr(runner, "run_baseline_scan", _should_not_run)

    await runner.run_strix_scan(
        scan_config={"targets": [], "scan_mode": "deep"},
        scan_id="scan-disabled",
        image="img",
        local_sources=[{"source_path": str(tmp_path / "repo")}],
    )

    assert called is False
    assert "baseline_scan_summary" not in captured["kwargs"]["system_prompt_context"]


@pytest.mark.asyncio
async def test_a_baseline_tool_crash_never_aborts_the_scan(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    """run_baseline_scan itself never raises (see its own tests), but the
    runner's own filing/persistence around it must be equally defensive —
    a bad finding must not prevent the rest of the scan from proceeding."""
    captured = _wire_runner(monkeypatch, tmp_path)

    bad_result = BaselineResult(
        findings=[
            BaselineFinding(category="dependencies", title="x", severity="high", target="y")
        ],
    )
    monkeypatch.setattr(runner, "run_baseline_scan", lambda *_a, **_k: bad_result)

    original_add = report_state_module.ReportState.add_vulnerability_report

    def _raise_once(_self: Any, *_args: Any, **_kwargs: Any) -> str:
        raise RuntimeError("persistence blew up")

    monkeypatch.setattr(report_state_module.ReportState, "add_vulnerability_report", _raise_once)

    await runner.run_strix_scan(
        scan_config={"targets": [], "scan_mode": "deep"},
        scan_id="scan-crash",
        image="img",
        local_sources=[{"source_path": str(tmp_path / "repo")}],
    )

    assert "kwargs" in captured  # the scan reached build_strix_agent despite the crash
    monkeypatch.setattr(report_state_module.ReportState, "add_vulnerability_report", original_add)
