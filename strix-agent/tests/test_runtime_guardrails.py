from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from strix.core import execution
from strix.core.agents import AgentCoordinator
from strix.runtime.docker_client import _apply_resource_limits


async def _noop_start_child_runner(**_kwargs):
    return None


def _factory(**_kwargs):
    return object()


@pytest.mark.asyncio
async def test_spawn_child_agent_enforces_total_child_limit(monkeypatch, tmp_path: Path):
    coordinator = AgentCoordinator()
    await coordinator.register("root", "Root", parent_id=None)
    await coordinator.register("existing", "Existing", parent_id="root")
    monkeypatch.setattr(
        execution,
        "load_settings",
        lambda: SimpleNamespace(runtime=SimpleNamespace(max_child_agents=1, max_agent_depth=3)),
    )
    monkeypatch.setattr(execution, "_start_child_runner", _noop_start_child_runner)

    result = await execution.spawn_child_agent(
        coordinator=coordinator,
        factory=_factory,
        agents_db_path=tmp_path / "agents.db",
        sessions_to_close=[],
        run_config=object(),
        max_turns=1,
        interactive=False,
        parent_ctx={"agent_id": "root"},
        name="Child",
        task="Do work",
        skills=[],
        parent_history=[],
    )

    assert result["success"] is False
    assert "limit reached" in result["error"]


@pytest.mark.asyncio
async def test_spawn_child_agent_ignores_finished_children_toward_the_cap(
    monkeypatch, tmp_path: Path
):
    coordinator = AgentCoordinator()
    await coordinator.register("root", "Root", parent_id=None)
    await coordinator.register("done", "Done", parent_id="root")
    await coordinator.set_status("done", "completed")
    monkeypatch.setattr(
        execution,
        "load_settings",
        lambda: SimpleNamespace(runtime=SimpleNamespace(max_child_agents=1, max_agent_depth=3)),
    )
    monkeypatch.setattr(execution, "_start_child_runner", _noop_start_child_runner)

    result = await execution.spawn_child_agent(
        coordinator=coordinator,
        factory=_factory,
        agents_db_path=tmp_path / "agents.db",
        sessions_to_close=[],
        run_config=object(),
        max_turns=1,
        interactive=False,
        parent_ctx={"agent_id": "root"},
        name="Next",
        task="Do work",
        skills=[],
        parent_history=[],
    )

    assert result["success"] is True
    assert execution.count_live_child_agents(coordinator) == 1


@pytest.mark.asyncio
async def test_spawn_child_agent_enforces_depth_limit(monkeypatch, tmp_path: Path):
    coordinator = AgentCoordinator()
    await coordinator.register("root", "Root", parent_id=None)
    await coordinator.register("level1", "Level 1", parent_id="root")
    monkeypatch.setattr(
        execution,
        "load_settings",
        lambda: SimpleNamespace(runtime=SimpleNamespace(max_child_agents=12, max_agent_depth=1)),
    )
    monkeypatch.setattr(execution, "_start_child_runner", _noop_start_child_runner)

    result = await execution.spawn_child_agent(
        coordinator=coordinator,
        factory=_factory,
        agents_db_path=tmp_path / "agents.db",
        sessions_to_close=[],
        run_config=object(),
        max_turns=1,
        interactive=False,
        parent_ctx={"agent_id": "level1"},
        name="Too Deep",
        task="Do work",
        skills=[],
        parent_history=[],
    )

    assert result["success"] is False
    assert "depth limit" in result["error"]


@pytest.mark.asyncio
async def test_spawn_child_agent_injects_scan_brief(monkeypatch, tmp_path: Path):
    captured: dict = {}

    async def capture(**kwargs):
        captured.update(kwargs)

    coordinator = AgentCoordinator()
    await coordinator.register("root", "Root", parent_id=None)
    monkeypatch.setattr(
        execution,
        "load_settings",
        lambda: SimpleNamespace(runtime=SimpleNamespace(max_child_agents=12, max_agent_depth=3)),
    )
    monkeypatch.setattr(execution, "_start_child_runner", capture)

    result = await execution.spawn_child_agent(
        coordinator=coordinator,
        factory=_factory,
        agents_db_path=tmp_path / "agents.db",
        sessions_to_close=[],
        run_config=object(),
        max_turns=1,
        interactive=False,
        parent_ctx={"agent_id": "root", "scan_targets": ["https://app.example"]},
        name="Child",
        task="Audit the login flow.",
        skills=[],
        parent_history=[],
    )

    assert result["success"] is True
    content = captured["initial_input"][0]["content"]
    assert "Scan brief" in content
    assert "https://app.example" in content
    assert "Audit the login flow." in content
    assert content.index("Scan brief") < content.index("Audit the login flow.")


def test_docker_resource_limits_default_on(monkeypatch):
    for key in (
        "STRIX_SANDBOX_MEM_LIMIT",
        "STRIX_SANDBOX_SHM_SIZE",
        "STRIX_SANDBOX_CPUS",
        "STRIX_SANDBOX_PIDS_LIMIT",
    ):
        monkeypatch.delenv(key, raising=False)

    create_kwargs = {}
    _apply_resource_limits(create_kwargs)

    assert create_kwargs["mem_limit"] == "4g"
    assert create_kwargs["shm_size"] == "1g"
    assert create_kwargs["nano_cpus"] == 4_000_000_000
    assert create_kwargs["pids_limit"] == 1024
