"""Tests for interface.utils.clone_repository's ref/commit-pinning support."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from strix.interface.utils import clone_repository


def _git(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)  # noqa: S603, S607


@pytest.fixture
def local_remote(tmp_path: Path) -> Path:
    """A throwaway local git repo (acting as the "remote") with two commits
    on main and a second branch, so tests can check out each independently."""
    remote = tmp_path / "remote"
    remote.mkdir()
    _git("init", "-b", "main", cwd=remote)
    _git("config", "user.email", "test@example.com", cwd=remote)
    _git("config", "user.name", "Test", cwd=remote)

    (remote / "file.txt").write_text("on main\n")
    _git("add", "file.txt", cwd=remote)
    _git("commit", "-m", "first commit on main", cwd=remote)

    _git("checkout", "-b", "feature", cwd=remote)
    (remote / "file.txt").write_text("on feature\n")
    _git("add", "file.txt", cwd=remote)
    _git("commit", "-m", "commit on feature", cwd=remote)

    _git("checkout", "main", cwd=remote)
    return remote


def test_clone_repository_defaults_to_the_remotes_current_head(local_remote: Path) -> None:
    path, resolved_sha = clone_repository(str(local_remote), run_name="run-1")

    assert (Path(path) / "file.txt").read_text() == "on main\n"
    expected_sha = _git("rev-parse", "main", cwd=local_remote).stdout.strip()
    assert resolved_sha == expected_sha


def test_clone_repository_checks_out_a_given_branch(local_remote: Path) -> None:
    path, resolved_sha = clone_repository(str(local_remote), run_name="run-2", ref="feature")

    assert (Path(path) / "file.txt").read_text() == "on feature\n"
    expected_sha = _git("rev-parse", "feature", cwd=local_remote).stdout.strip()
    assert resolved_sha == expected_sha
    assert resolved_sha != _git("rev-parse", "main", cwd=local_remote).stdout.strip()


def test_clone_repository_checks_out_a_given_commit_sha(local_remote: Path) -> None:
    target_sha = _git("rev-parse", "main", cwd=local_remote).stdout.strip()

    path, resolved_sha = clone_repository(str(local_remote), run_name="run-3", ref=target_sha)

    assert resolved_sha == target_sha
    assert (Path(path) / "file.txt").read_text() == "on main\n"


def test_clone_repository_raises_a_clear_error_for_an_unknown_ref(local_remote: Path) -> None:
    with pytest.raises(ValueError, match="Could not check out ref 'does-not-exist'"):
        clone_repository(str(local_remote), run_name="run-4", ref="does-not-exist")
