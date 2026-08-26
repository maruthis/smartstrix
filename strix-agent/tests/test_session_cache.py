from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from strix.runtime import session_manager


class _Gone:
    def get(self, _container_id: str) -> None:
        raise RuntimeError("not found")


class _Stopped:
    def get(self, _container_id: str) -> SimpleNamespace:
        return SimpleNamespace(status="exited")


class _Running:
    def get(self, _container_id: str) -> SimpleNamespace:
        return SimpleNamespace(status="running")


def _bundle(containers: Any, container_id: str = "abc") -> dict[str, Any]:
    inner = SimpleNamespace(state=SimpleNamespace(container_id=container_id))
    session = SimpleNamespace(_inner=inner)
    client = SimpleNamespace(docker_client=SimpleNamespace(containers=containers))
    return {"client": client, "session": session}


def test_cached_session_without_docker_is_treated_as_alive() -> None:
    bundle = {"client": object(), "session": object()}
    assert session_manager._cached_session_is_alive(bundle) is True


def test_cached_session_is_dead_when_container_is_gone() -> None:
    assert session_manager._cached_session_is_alive(_bundle(_Gone())) is False


def test_cached_session_is_dead_when_container_is_stopped() -> None:
    assert session_manager._cached_session_is_alive(_bundle(_Stopped())) is False


def test_cached_session_is_alive_when_container_is_running() -> None:
    assert session_manager._cached_session_is_alive(_bundle(_Running())) is True


@pytest.mark.asyncio
async def test_create_or_reuse_drops_a_dead_cache_entry(monkeypatch: pytest.MonkeyPatch) -> None:
    dead = _bundle(_Gone())
    session_manager._SESSION_CACHE["scan-1"] = dead

    monkeypatch.setattr(
        session_manager,
        "load_settings",
        lambda: SimpleNamespace(runtime=SimpleNamespace(backend="docker")),
    )

    def _raise(_name: str) -> None:
        raise RuntimeError("create path reached")

    monkeypatch.setattr(session_manager, "get_backend", _raise)

    with pytest.raises(RuntimeError, match="create path reached"):
        await session_manager.create_or_reuse("scan-1", image="strix", local_sources=[])
    assert "scan-1" not in session_manager._SESSION_CACHE
